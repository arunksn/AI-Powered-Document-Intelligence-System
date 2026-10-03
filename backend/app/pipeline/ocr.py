"""
OCR for scanned PDFs and images (Section 1).

Uses Tesseract (via pytesseract) -- runs as an external OS process, so it
doesn't count against the Python-resident model memory budget (see
model_manager.py docstring).

Post-processing corrects common scanning artefacts:
  - broken words split across line breaks ("con-\\ntract" -> "contract")
  - common ligature misreads (fi/fl/ff glyphs OCR'd as odd unicode)
  - skew correction before OCR via OpenCV, rather than fixing after the fact

If mean word confidence falls below settings.OCR_CONFIDENCE_THRESHOLD, the
result is flagged low_quality rather than silently returned.
"""
import re
import logging

from app.config import settings

logger = logging.getLogger("ocr")

LIGATURE_FIXES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
    "\ufb03": "ffi", "\ufb04": "ffl",
    "ﬁ": "fi", "ﬂ": "fl",
}


def _deskew(image):
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.shape[0] < 20:
        return image  # not enough signal to estimate skew reliably
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    # minAreaRect over a full multi-line page (rather than a single text
    # line/blob) frequently produces a spurious large-angle result -- e.g.
    # computing a 90-degree "correction" for an already-straight page,
    # which destroys the scan instead of fixing it. Genuine scanner skew
    # is a few degrees at most, so treat anything beyond that as noise
    # from the heuristic rather than real skew, and leave the image alone.
    if abs(angle) < 0.1 or abs(angle) > 15:
        return image
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    m = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(image, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _fix_ligatures(text: str) -> str:
    for bad, good in LIGATURE_FIXES.items():
        text = text.replace(bad, good)
    return text


def _fix_broken_words(text: str) -> str:
    # "exam-\nple" -> "example"; hyphen at end of line followed by lowercase
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Collapse stray single-newlines mid-sentence (OCR line wrap) while
    # preserving genuine paragraph breaks (double newline).
    text = re.sub(r"(?<!\n)\n(?!\n)(?=[a-z])", " ", text)
    return text


def _postprocess(raw_text: str) -> str:
    text = _fix_ligatures(raw_text)
    text = _fix_broken_words(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _group_words_into_lines(data: dict) -> tuple[str, float]:
    """Pure function: takes pytesseract's image_to_data() output dict and
    reconstructs line-broken text, grouping words by (block_num, par_num,
    line_num) rather than space-joining everything. Separated from the
    actual pytesseract/cv2 calls so it can be unit tested with a plain
    dict fixture, no image or OCR engine required."""
    n = len(data["text"])
    confidences = []
    lines: dict[tuple, list[str]] = {}
    line_order: list[tuple] = []
    for i in range(n):
        word = data["text"][i]
        if not word.strip():
            continue
        conf = data["conf"][i]
        if conf != -1:
            confidences.append(int(conf))
        # (block_num, par_num, line_num) uniquely identifies a visual line --
        # grouping on this (rather than space-joining every word in the
        # image) is what lets downstream regexes rely on line boundaries,
        # e.g. distinguishing "Due Date: X" from the next printed line.
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if key not in lines:
            lines[key] = []
            line_order.append(key)
        lines[key].append(word)

    text = "\n".join(" ".join(lines[k]) for k in line_order)
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return text, mean_conf


def _ocr_single_image_array(img_array) -> dict:
    import pytesseract

    deskewed = _deskew(img_array)
    data = pytesseract.image_to_data(
        deskewed, lang=settings.OCR_LANGUAGES, output_type=pytesseract.Output.DICT
    )
    text, mean_conf = _group_words_into_lines(data)
    return {"text": text, "confidence": mean_conf}


def run_ocr_on_image(filepath: str) -> dict:
    from PIL import Image
    import numpy as np
    import cv2
    import fitz

    img = None
    # Strategy 1: PIL Image.open
    try:
        with Image.open(filepath) as pil_img:
            pil_img = pil_img.convert("RGB")
            img = np.array(pil_img)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    except Exception:
        pass

    # Strategy 2: OpenCV imdecode with np.fromfile (handles raw bytes & non-ASCII paths)
    if img is None:
        try:
            img_data = np.fromfile(filepath, dtype=np.uint8)
            decoded = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
            if decoded is not None and decoded.size > 0:
                img = decoded
        except Exception:
            pass

    # Strategy 3: PyMuPDF fitz (handles rasterized images, TIFFs, etc.)
    if img is None:
        try:
            doc = fitz.open(filepath)
            if len(doc) > 0:
                pix = doc[0].get_pixmap(dpi=300)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                if pix.n == 4:
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                elif pix.n == 1:
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                else:
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            doc.close()
        except Exception:
            pass

    # Fallback if image file is completely unreadable/empty
    if img is None:
        logger.warning(f"Could not decode image at {filepath} with any decoder.")
        return {"text": "(No readable text extracted from image)", "confidence": 0.0}

    result = _ocr_single_image_array(img)
    result["text"] = _postprocess(result["text"])
    return result


def run_ocr_on_pdf(filepath: str) -> dict:
    """Rasterizes each page of a scanned PDF and OCRs it."""
    import fitz
    import numpy as np
    import cv2

    doc = fitz.open(filepath)
    all_text = []
    all_confidences = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            elif pix.n == 1:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            else:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            page_result = _ocr_single_image_array(img)
            all_text.append(page_result["text"])
            if page_result["confidence"] > 0:
                all_confidences.append(page_result["confidence"])
    finally:
        doc.close()

    mean_conf = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
    return {"text": _postprocess("\n\n".join(all_text)), "confidence": mean_conf}


def is_low_quality(confidence: float) -> bool:
    return confidence < settings.OCR_CONFIDENCE_THRESHOLD
