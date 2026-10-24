"""The web and worker services don't share a disk on Railway, so the worker
must be able to rebuild the original upload from the database."""
import os

from app import models
from app.tasks import _ensure_local_file


def _make_document(db_session, filepath):
    user = models.User(email="w@acme.test", hashed_password="x")
    db_session.add(user)
    db_session.flush()
    project = models.Project(name="P", owner_id=user.id)
    db_session.add(project)
    db_session.flush()
    doc = models.Document(project_id=project.id, filename="contract.pdf", filepath=filepath)
    db_session.add(doc)
    db_session.flush()
    return doc


def test_worker_restores_upload_missing_from_local_disk(db_session, tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "worker"))
    doc = _make_document(db_session, "/nonexistent/web-service-disk/contract.pdf")
    db_session.add(models.DocumentFile(document_id=doc.id, data=b"%PDF-1.4 bytes"))
    db_session.commit()

    path = _ensure_local_file(db_session, doc)

    assert path.startswith(str(tmp_path / "worker"))
    with open(path, "rb") as f:
        assert f.read() == b"%PDF-1.4 bytes"


def test_existing_local_file_is_used_directly(db_session, tmp_path):
    local = tmp_path / "contract.pdf"
    local.write_bytes(b"x")
    doc = _make_document(db_session, str(local))
    assert _ensure_local_file(db_session, doc) == str(local)


def test_deleting_document_removes_stored_bytes(db_session):
    doc = _make_document(db_session, "/nonexistent")
    db_session.add(models.DocumentFile(document_id=doc.id, data=b"x"))
    db_session.commit()
    db_session.delete(doc)
    db_session.commit()
    assert db_session.query(models.DocumentFile).count() == 0
