"""
Orchestrates the full pipeline for a document as a single Celery task
(stages run in sequence within one task, not as separate queued tasks,
so a document's stages can never race or get processed out of order --
see celery_app.py comment on worker_prefetch_multiplier).

Each stage: mark active -> publish WS update -> do work -> persist ->
mark complete -> publish WS update. This is what lets the frontend show
each stage's spinner-then-checkmark-then-output-panel in real time.
"""
import hashlib
import logging
import traceback
from app.utils import utcnow

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import (
    Document, Project, PipelineStageResult, Anomaly, Contradiction,
    CrmSyncRecord, ProcessingStatus,
)
from app.websocket_manager import publish_stage_update
from app.pipeline import ingestion, classification, extraction, anomaly_detection, risk_scoring
from app.pipeline import contradiction_detection, crm_sync
from app.config import settings

logger = logging.getLogger("tasks")

STAGE_NAMES = {
    0: "Ingestion & Normalisation",
    1: "Document Classification",
    2: "Entity & Clause Extraction",
    3: "Anomaly Detection",
    4: "Risk Scoring",
    5: "Cross-Document Contradiction Check",
}


def _set_stage(db, document_id: str, stage_number: int, status: str, output: dict | None = None):
    row = (
        db.query(PipelineStageResult)
        .filter_by(document_id=document_id, stage_number=stage_number)
        .first()
    )
    if row is None:
        row = PipelineStageResult(
            document_id=document_id, stage_number=stage_number,
            stage_name=STAGE_NAMES[stage_number],
        )
        db.add(row)
    row.status = status
    if output is not None:
        row.output = output
    if status == "active":
        row.started_at = utcnow()
    if status in ("complete", "failed"):
        row.completed_at = utcnow()
    db.commit()

    publish_stage_update(document_id, {
        "type": "stage_update",
        "document_id": document_id,
        "stage_number": stage_number,
        "stage_name": STAGE_NAMES[stage_number],
        "status": status,
        "output": output if status == "complete" else None,
    })


@celery_app.task(bind=True, max_retries=1)
def process_document_task(self, document_id: str):
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.error("Document %s not found", document_id)
            return

        document.status = ProcessingStatus.processing
        db.commit()
        publish_stage_update(document_id, {"type": "status", "status": "processing"})

        # --- Stage 0: Ingestion & Normalisation ---
        _set_stage(db, document_id, 0, "active")
        normalized = ingestion.normalize_document(document.filepath, document.filename)

        document.is_scanned = normalized["is_scanned"]
        document.ocr_confidence = normalized["ocr_confidence"]
        if normalized["is_scanned"] and normalized["ocr_confidence"] is not None:
            document.low_quality_flag = normalized["ocr_confidence"] < settings.OCR_CONFIDENCE_THRESHOLD
        document.normalized_structure = {
            "sections": normalized["sections"][:200],  # cap stored size
            "tables_count": len(normalized["tables"]),
        }
        document.current_stage = 0
        db.commit()
        _set_stage(db, document_id, 0, "complete", {
            "is_scanned": normalized["is_scanned"],
            "ocr_confidence": normalized["ocr_confidence"],
            "low_quality_flag": document.low_quality_flag,
            "sections_found": len(normalized["sections"]),
            "tables_found": len(normalized["tables"]),
        })

        raw_text = normalized["raw_text"]
        tables = normalized["tables"]

        # --- Stage 1: Classification ---
        _set_stage(db, document_id, 1, "active")
        stage1 = classification.run_stage1(raw_text)
        document.document_type = stage1["document_type"]
        document.primary_parties = stage1["primary_parties"]
        document.key_dates = stage1["key_dates"]
        document.governing_jurisdiction = stage1["governing_jurisdiction"]
        document.current_stage = 1
        db.commit()
        _set_stage(db, document_id, 1, "complete", stage1)

        # --- Stage 2: Entity & Clause Extraction ---
        _set_stage(db, document_id, 2, "active")
        stage2 = extraction.run_stage2(document.document_type, raw_text, tables)
        document.extracted_entities = stage2
        # Invoice vendors are first-class counterparties. Keep the vendor in
        # the document's primary-party field as well as the type-specific
        # extraction so CRM records and cross-document matching remain useful
        # even when the lightweight NER model misses the vendor name.
        if document.document_type == "invoice":
            vendor = stage2.get("vendor")
            parties = list(document.primary_parties or [])
            if vendor and vendor not in parties:
                parties.append(vendor)
            document.primary_parties = parties[:8]
        document.current_stage = 2
        db.commit()
        _set_stage(db, document_id, 2, "complete", stage2)

        # --- Stage 3: Anomaly Detection ---
        _set_stage(db, document_id, 3, "active")
        anomalies = anomaly_detection.run_stage3(document.document_type, stage2)
        db.query(Anomaly).filter_by(document_id=document_id).delete()
        for a in anomalies:
            db.add(Anomaly(document_id=document_id, **a))
        document.current_stage = 3
        db.commit()
        _set_stage(db, document_id, 3, "complete", {"anomalies": anomalies})

        # --- Stage 4: Risk Scoring ---
        _set_stage(db, document_id, 4, "active")
        stage4 = risk_scoring.run_stage4(anomalies)
        document.risk_score = stage4["risk_score"]
        document.risk_breakdown = stage4
        document.current_stage = 4
        db.commit()
        _set_stage(db, document_id, 4, "complete", stage4)

        # --- Stage 5: project-level contradiction detection ---
        # If this is currently the only completed document, explicitly mark
        # the stage as skipped. A later upload will replace it with an active
        # Stage 5 result once the project has at least two completed documents.
        completed_count = (
            db.query(Document)
            .filter(Document.project_id == document.project_id, Document.status == ProcessingStatus.complete)
            .count()
        )
        if completed_count < 2:
            _set_stage(db, document_id, 5, "skipped", {
                "skipped": True,
                "reason": "Cross-document checks require at least two completed documents in the project.",
            })
        else:
            run_contradiction_detection_task.delay(document.project_id)

        document.current_stage = 5
        document.status = ProcessingStatus.complete
        db.commit()
        publish_stage_update(document_id, {"type": "status", "status": "complete"})

        # A second document may have been uploaded while this task was
        # finishing; ensure the project-level check is queued for every
        # completed-document transition.
        run_contradiction_detection_task.delay(document.project_id)

        # --- CRM sync, fire-and-forget-ish (own task so a CRM outage
        # doesn't block/fail the pipeline itself) ---
        sync_document_to_crm_task.delay(document_id)

    except Exception as exc:  # noqa: BLE001
        logger.error("Pipeline failed for %s: %s", document_id, traceback.format_exc())
        document = db.get(Document, document_id)
        if document:
            document.status = ProcessingStatus.failed
            document.error_message = str(exc)
            db.commit()
        publish_stage_update(document_id, {"type": "status", "status": "failed", "error": str(exc)})
    finally:
        db.close()


@celery_app.task
def run_contradiction_detection_task(project_id: str):
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if project is None:
            return
        docs = [d for d in project.documents if d.status == ProcessingStatus.complete]
        if len(docs) < 2:
            return

        doc_dicts = [
            {
                "id": d.id,
                "document_type": d.document_type,
                "extracted_entities": d.extracted_entities or {},
                "primary_parties": d.primary_parties or [],
            }
            for d in docs
        ]
        for d in docs:
            _set_stage(db, d.id, 5, "active")

        found = contradiction_detection.find_contradictions(doc_dicts)

        db.query(Contradiction).filter_by(project_id=project_id).delete()
        for c in found:
            db.add(Contradiction(project_id=project_id, **c))
        db.commit()

        stage5_output = {
            "contradiction_count": len(found),
            "project_id": project_id,
            "documents_compared": len(docs),
        }
        for doc_id in {d.id for d in docs}:
            _set_stage(db, doc_id, 5, "complete", stage5_output)
            publish_stage_update(doc_id, {
                "type": "contradictions_updated",
                "project_id": project_id,
                "contradiction_count": len(found),
            })
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def sync_document_to_crm_task(self, document_id: str):
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        project = db.get(Project, document.project_id)

        sync_row = db.query(CrmSyncRecord).filter_by(document_id=document_id).first()
        if sync_row is None:
            sync_row = CrmSyncRecord(document_id=document_id, provider=settings.CRM_PROVIDER)
            db.add(sync_row)
            db.commit()

        try:
            external_id = crm_sync.sync_document_to_crm(document, project)
            sync_row.external_record_id = external_id
            sync_row.status = "synced"
            sync_row.last_error = None
            sync_row.last_synced_at = utcnow()
        except ValueError as exc:
            sync_row.status = "failed"
            sync_row.last_error = str(exc)
            db.commit()
            publish_stage_update(document_id, {"type": "crm_sync_update", "status": sync_row.status})
            return
        except Exception as exc:  # noqa: BLE001
            sync_row.status = "failed"
            sync_row.last_error = str(exc)
            db.commit()
            publish_stage_update(document_id, {"type": "crm_sync_update", "status": sync_row.status})
            if self.request.retries >= self.max_retries:
                return
            raise self.retry(exc=exc)
        db.commit()
        publish_stage_update(document_id, {"type": "crm_sync_update", "status": sync_row.status})
    finally:
        db.close()


def compute_content_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()
