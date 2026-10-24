import uuid
import enum
from app.utils import utcnow
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, ForeignKey, JSON, Enum, Boolean, LargeBinary
)
from sqlalchemy.orm import relationship
from app.database import Base


def gen_id() -> str:
    return str(uuid.uuid4())


class DocumentType(str, enum.Enum):
    contract = "contract"
    invoice = "invoice"
    financial_statement = "financial_statement"
    rfp = "rfp"
    nda = "nda"
    other = "other"


class ProcessingStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class Severity(str, enum.Enum):
    critical = "critical"
    warning = "warning"
    informational = "informational"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    email = Column(String, nullable=False, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String, default="")
    created_at = Column(DateTime, default=utcnow)

    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=gen_id)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="projects")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    contradictions = relationship("Contradiction", back_populates="project", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=gen_id)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)

    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)  # ephemeral local path used during processing
    content_hash = Column(String, index=True)  # sha256 of original bytes, used for CRM upsert
    source_format = Column(String)  # pdf | docx | xlsx | jpg | png
    is_scanned = Column(Boolean, default=False)
    ocr_confidence = Column(Float, nullable=True)
    low_quality_flag = Column(Boolean, default=False)

    status = Column(Enum(ProcessingStatus), default=ProcessingStatus.queued)
    current_stage = Column(Integer, default=0)  # 0-5
    error_message = Column(Text, nullable=True)

    document_type = Column(Enum(DocumentType), nullable=True)
    primary_parties = Column(JSON, default=list)
    key_dates = Column(JSON, default=dict)
    governing_jurisdiction = Column(String, nullable=True)

    normalized_structure = Column(JSON, default=dict)  # headings/sections/tables from Stage 0
    extracted_entities = Column(JSON, default=dict)    # Stage 2 output
    risk_score = Column(Float, nullable=True)
    risk_breakdown = Column(JSON, default=dict)        # Stage 4 output

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="documents")
    anomalies = relationship("Anomaly", back_populates="document", cascade="all, delete-orphan")
    stage_results = relationship("PipelineStageResult", back_populates="document", cascade="all, delete-orphan")
    crm_sync = relationship("CrmSyncRecord", back_populates="document", uselist=False, cascade="all, delete-orphan")
    original_file = relationship("DocumentFile", uselist=False, cascade="all, delete-orphan")


class PipelineStageResult(Base):
    """One row per (document, stage) so the processing view can render
    completed stages immediately on page reload, not just live via WS."""
    __tablename__ = "pipeline_stage_results"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    stage_number = Column(Integer, nullable=False)
    stage_name = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending | active | complete | failed
    output = Column(JSON, default=dict)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    document = relationship("Document", back_populates="stage_results")


class Anomaly(Base):
    __tablename__ = "anomalies"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    severity = Column(Enum(Severity), nullable=False)
    category = Column(String)  # e.g. "termination_notice", "amount_mismatch"
    explanation = Column(Text)
    evidence = Column(JSON, default=dict)  # the specific values that triggered the flag
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="anomalies")


class Contradiction(Base):
    __tablename__ = "contradictions"

    id = Column(String, primary_key=True, default=gen_id)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)
    document_a_id = Column(String, ForeignKey("documents.id"))
    document_b_id = Column(String, ForeignKey("documents.id"))
    field = Column(String)  # e.g. "payment_terms_days", "revenue"
    value_a = Column(String)
    value_b = Column(String)
    explanation = Column(Text)
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="contradictions")


class CrmSyncRecord(Base):
    __tablename__ = "crm_sync_records"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    provider = Column(String)
    external_record_id = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | synced | failed
    last_error = Column(Text, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)

    document = relationship("Document", back_populates="crm_sync")


class DocumentFile(Base):
    """Original upload bytes. The web and worker run as separate services on
    Railway (and separate containers in docker-compose), so a file written
    to the web service's local disk is invisible to the worker; the worker
    restores it from here instead. Also makes reprocessing survive restarts
    of the ephemeral filesystem."""
    __tablename__ = "document_files"

    document_id = Column(String, ForeignKey("documents.id"), primary_key=True)
    data = Column(LargeBinary, nullable=False)
