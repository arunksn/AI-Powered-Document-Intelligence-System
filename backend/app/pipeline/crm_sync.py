"""
Section 3: CRM Sync.

Pushes a structured record to Notion or Airtable after processing.
Upserts by content_hash: if a record with the same hash already exists
in the CRM, it's updated in place rather than duplicated.
"""
import requests
from app.config import settings


def build_record_payload(document, project) -> dict:
    counts = {"critical": 0, "warning": 0, "informational": 0}
    for a in document.anomalies:
        counts[a.severity] = counts.get(a.severity, 0) + 1

    return {
        "content_hash": document.content_hash,
        "document_type": document.document_type,
        "filename": document.filename,
        "project_name": project.name,
        "primary_parties": ", ".join(document.primary_parties or []),
        "key_fields": document.extracted_entities,
        "anomaly_critical": counts.get("critical", 0),
        "anomaly_warning": counts.get("warning", 0),
        "anomaly_informational": counts.get("informational", 0),
        "risk_score": document.risk_score,
        "processed_at": document.updated_at.isoformat() if document.updated_at else None,
        "platform_link": f"{settings.PUBLIC_APP_URL.rstrip('/')}/documents/{document.id}",
    }


def _find_existing_notion_page(db_id: str, api_key: str, content_hash: str) -> str | None:
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    body = {"filter": {"property": "ContentHash", "rich_text": {"equals": content_hash}}}
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0]["id"] if results else None
    except requests.exceptions.HTTPError as err:
        try:
            err_data = resp.json()
            msg = err_data.get("message", str(err))
        except Exception:
            msg = str(err)
        raise ValueError(f"Notion API error: {msg}") from err
    except requests.exceptions.RequestException as err:
        raise ValueError(f"Notion connection error: {err}") from err


def sync_to_notion(payload: dict) -> str:
    api_key = (settings.NOTION_API_KEY or "").strip()
    db_id = (settings.NOTION_DATABASE_ID or "").strip().strip("/")

    if not api_key or not db_id:
        raise ValueError(
            "Notion CRM is not configured. Please set NOTION_API_KEY and NOTION_DATABASE_ID in backend/.env"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    properties = {
        "Name": {"title": [{"text": {"content": payload["filename"]}}]},
        "ContentHash": {"rich_text": [{"text": {"content": payload["content_hash"] or ""}}]},
        "DocumentType": {"select": {"name": payload["document_type"] or "other"}},
        "Project": {"rich_text": [{"text": {"content": payload["project_name"]}}]},
        "PrimaryParties": {"rich_text": [{"text": {"content": payload["primary_parties"][:1900]}}]},
        "RiskScore": {"number": payload["risk_score"] or 0},
        "CriticalAnomalies": {"number": payload["anomaly_critical"]},
        "WarningAnomalies": {"number": payload["anomaly_warning"]},
        "InfoAnomalies": {"number": payload["anomaly_informational"]},
        "PlatformLink": {"url": payload["platform_link"] if payload["platform_link"].startswith("http") else None},
    }

    try:
        existing_id = _find_existing_notion_page(db_id, api_key, payload["content_hash"]) if payload["content_hash"] else None
        if existing_id:
            url = f"https://api.notion.com/v1/pages/{existing_id}"
            resp = requests.patch(url, headers=headers, json={"properties": properties}, timeout=15)
            resp.raise_for_status()
            return existing_id
        else:
            url = "https://api.notion.com/v1/pages"
            body = {"parent": {"database_id": db_id}, "properties": properties}
            resp = requests.post(url, headers=headers, json=body, timeout=15)
            resp.raise_for_status()
            return resp.json()["id"]
    except requests.exceptions.HTTPError as err:
        try:
            err_data = resp.json()
            msg = err_data.get("message", str(err))
        except Exception:
            msg = str(err)
        raise ValueError(f"Notion API error: {msg}") from err
    except requests.exceptions.RequestException as err:
        raise ValueError(f"Notion connection error: {err}") from err


def _find_existing_airtable_record(base_id: str, table_name: str, api_key: str, content_hash: str) -> str | None:
    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"filterByFormula": f"{{ContentHash}}='{content_hash}'"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        records = resp.json().get("records", [])
        return records[0]["id"] if records else None
    except Exception as err:
        raise ValueError(f"Airtable API error: {err}") from err


def sync_to_airtable(payload: dict) -> str:
    api_key = (settings.AIRTABLE_API_KEY or "").strip()
    base_id = (settings.AIRTABLE_BASE_ID or "").strip()
    table_name = (settings.AIRTABLE_TABLE_NAME or "").strip()

    if not api_key or not base_id or not table_name:
        raise ValueError(
            "Airtable CRM is not configured. Please set AIRTABLE_API_KEY, AIRTABLE_BASE_ID, and AIRTABLE_TABLE_NAME in backend/.env"
        )

    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    fields = {
        "Name": payload["filename"],
        "ContentHash": payload["content_hash"],
        "DocumentType": payload["document_type"],
        "Project": payload["project_name"],
        "PrimaryParties": payload["primary_parties"],
        "RiskScore": payload["risk_score"] or 0,
        "CriticalAnomalies": payload["anomaly_critical"],
        "WarningAnomalies": payload["anomaly_warning"],
        "InfoAnomalies": payload["anomaly_informational"],
        "PlatformLink": payload["platform_link"],
    }
    try:
        existing_id = _find_existing_airtable_record(base_id, table_name, api_key, payload["content_hash"]) if payload["content_hash"] else None
        if existing_id:
            resp = requests.patch(f"{url}/{existing_id}", headers=headers, json={"fields": fields}, timeout=15)
            resp.raise_for_status()
            return existing_id
        else:
            resp = requests.post(url, headers=headers, json={"fields": fields}, timeout=15)
            resp.raise_for_status()
            return resp.json()["id"]
    except Exception as err:
        raise ValueError(f"Airtable API error: {err}") from err


def sync_document_to_crm(document, project) -> str:
    payload = build_record_payload(document, project)
    provider = (settings.CRM_PROVIDER or "").lower().strip()
    if provider == "airtable":
        api_key = (settings.AIRTABLE_API_KEY or "").strip()
        base_id = (settings.AIRTABLE_BASE_ID or "").strip()
        if not api_key or not base_id:
            return f"mock-airtable-{document.id[:8]}"
        return sync_to_airtable(payload)
    elif provider == "mock":
        return f"mock-rec-{document.id[:8]}"

    # Default: Notion
    api_key = (settings.NOTION_API_KEY or "").strip()
    db_id = (settings.NOTION_DATABASE_ID or "").strip().strip("/")
    if not api_key or not db_id:
        return f"mock-notion-{document.id[:8]}"
    return sync_to_notion(payload)

