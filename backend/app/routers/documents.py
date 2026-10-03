import os
import uuid
import threading

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.config import settings
from app.auth import get_current_user
from app.tasks import process_document_task, sync_document_to_crm_task, compute_content_hash
from app.pipeline.ingestion import detect_format

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "jpg", "jpeg", "png"}


def _dispatch_processing_task(doc_id: str):
    try:
        process_document_task.delay(doc_id)
    except Exception:
        # Fallback to direct background thread if Celery broker is unavailable
        threading.Thread(target=lambda: process_document_task.apply(args=[doc_id]), daemon=True).start()




def _get_owned_document(document_id: str, current_user: models.User, db: Session) -> models.Document:
    """A document's ownership is derived from its project's owner_id --
    documents don't carry owner_id directly to avoid it ever drifting out
    of sync with the project it belongs to."""
    document = db.get(models.Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    project = db.get(models.Project, document.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(404, "Document not found")
    return document


@router.post("/upload", response_model=schemas.DocumentOut)
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.get(models.Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(404, "Project not found")

    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type .{ext}. Allowed: {sorted(ALLOWED_EXTENSIONS)}")

    try:
        detect_format(file.filename)
    except ValueError as e:
        raise HTTPException(400, str(e))

    doc_id = str(uuid.uuid4())
    dest_path = os.path.join(settings.UPLOAD_DIR, f"{doc_id}_{file.filename}")

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    content_hash = compute_content_hash(contents)

    document = models.Document(
        id=doc_id,
        project_id=project_id,
        filename=file.filename,
        filepath=dest_path,
        content_hash=content_hash,
        source_format=ext,
        status=models.ProcessingStatus.queued,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    _dispatch_processing_task(document.id)

    return document



@router.get("/{document_id}", response_model=schemas.DocumentOut)
def get_document(
    document_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _get_owned_document(document_id, current_user, db)


@router.get("/{document_id}/stages")
def get_document_stages(
    document_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_document(document_id, current_user, db)
    rows = (
        db.query(models.PipelineStageResult)
        .filter_by(document_id=document_id)
        .order_by(models.PipelineStageResult.stage_number)
        .all()
    )
    return [
        {
            "stage_number": r.stage_number,
            "stage_name": r.stage_name,
            "status": r.status,
            "output": r.output,
        }
        for r in rows
    ]


@router.get("/{document_id}/anomalies", response_model=list[schemas.AnomalyOut])
def get_document_anomalies(
    document_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_document(document_id, current_user, db)
    return db.query(models.Anomaly).filter_by(document_id=document_id).all()


@router.get("/{document_id}/crm-sync", response_model=schemas.CrmSyncOut)
def get_crm_sync_status(
    document_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_document(document_id, current_user, db)
    row = db.query(models.CrmSyncRecord).filter_by(document_id=document_id).first()
    if not row:
        raise HTTPException(404, "No CRM sync record yet")
    return row


@router.post("/{document_id}/crm-sync/retry")
def retry_crm_sync(
    document_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_document(document_id, current_user, db)
    sync_document_to_crm_task.delay(document_id)
    return {"queued": True}


@router.post("/{document_id}/reprocess")
def reprocess_document(
    document_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = _get_owned_document(document_id, current_user, db)
    if not os.path.exists(document.filepath):
        raise HTTPException(410, "Original file no longer available on disk (ephemeral storage) -- re-upload to reprocess.")
    document.status = models.ProcessingStatus.queued
    document.current_stage = 0
    db.commit()
    _dispatch_processing_task(document_id)
    return {"queued": True}



@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = _get_owned_document(document_id, current_user, db)
    if document.filepath and os.path.exists(document.filepath):
        try:
            os.remove(document.filepath)
        except OSError:
            pass
    db.delete(document)
    db.commit()
    return {"deleted": True}
