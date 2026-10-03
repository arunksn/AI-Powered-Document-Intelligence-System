"""
Memory management strategy (also documented in README):

Railway's free tier gives each service ~512MB-1GB RAM. A spaCy NER model,
a sentence-transformers embedding model, and Tesseract OCR data files
cannot all sit resident in the same worker process simultaneously without
risking OOM kills, especially with several documents processing at once.

Strategy implemented here: a single-process, lazy-loading, idle-unloading
model registry.

  - Models are NOT loaded at worker startup. They load on first use
    (lazy loading), so a worker that only ever OCRs images never pays the
    spaCy load cost, and vice versa.
  - Only ONE heavyweight model is resident at a time (MAX_CONCURRENT_MODELS,
    default 1). Requesting a different model evicts the current one first
    (model cycling) rather than stacking them in memory.
  - A background watchdog thread unloads a model after
    MODEL_IDLE_UNLOAD_SECONDS of no use, freeing memory between documents
    without requiring an explicit "close" call from pipeline code.
  - Tesseract is invoked as an external OS process (via pytesseract), not
    a Python-resident model, so it does not count against this budget --
    it's cheap to spawn per-document and exits when done.

This keeps steady-state memory bounded to "one small model + FastAPI/
Celery overhead" regardless of how many pipeline stages a document has
passed through.
"""
import threading
import time
import logging

from app.config import settings

logger = logging.getLogger("model_manager")

_lock = threading.Lock()
_loaded: dict[str, object] = {}
_last_used: dict[str, float] = {}
_watchdog_started = False


def _loader_for(name: str):
    if name == "spacy_ner":
        def _load():
            import spacy
            try:
                return spacy.load("en_core_web_sm")
            except Exception as err:
                logger.warning("Failed to load en_core_web_sm (%s), attempting dynamic download...", err)
                try:
                    import subprocess, sys
                    subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"], check=True)
                    return spacy.load("en_core_web_sm")
                except Exception as dl_err:
                    logger.error("Could not download en_core_web_sm, falling back to spacy.blank('en'): %s", dl_err)
                    return spacy.blank("en")
        return _load
    raise ValueError(f"Unknown model: {name}")



def _evict_all_except(keep: str | None):
    for name in list(_loaded.keys()):
        if name != keep:
            logger.info("Evicting model '%s' to respect MAX_CONCURRENT_MODELS", name)
            del _loaded[name]
            _last_used.pop(name, None)


def get_model(name: str):
    """Returns a loaded model, loading (and evicting others) if needed."""
    global _watchdog_started
    with _lock:
        if name not in _loaded:
            if len(_loaded) >= settings.MAX_CONCURRENT_MODELS:
                _evict_all_except(keep=None)
            logger.info("Loading model '%s'", name)
            _loaded[name] = _loader_for(name)()
        _last_used[name] = time.time()
        if not _watchdog_started:
            _watchdog_started = True
            threading.Thread(target=_idle_watchdog, daemon=True).start()
        return _loaded[name]


def _idle_watchdog():
    while True:
        time.sleep(15)
        now = time.time()
        with _lock:
            for name in list(_loaded.keys()):
                if now - _last_used.get(name, now) > settings.MODEL_IDLE_UNLOAD_SECONDS:
                    logger.info("Unloading idle model '%s'", name)
                    del _loaded[name]
                    _last_used.pop(name, None)
