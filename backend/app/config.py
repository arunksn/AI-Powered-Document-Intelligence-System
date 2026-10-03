import os
import json
class Settings:
    # Core
    ENV: str = os.getenv("ENV", "development")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")

    # Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-jwt-secret-change-me-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))  # 7 days

    # Database
    # Railway injects DATABASE_URL for its Postgres plugin. Falls back to
    # local sqlite file for dev so you don't need Postgres running locally.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./docintel.db")

    # --- Redis (Celery broker/backend + WebSocket pub/sub fan-out) ---
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # File storage 
    # Railway free tier has an ephemeral filesystem, so uploaded originals
    # are stored just long enough to run the pipeline, then discarded.
    # Extracted structured data (the valuable part) lives in Postgres/SQLite.
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "/tmp/docintel_uploads")

    # OCR
    OCR_CONFIDENCE_THRESHOLD: float = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "60.0"))
    OCR_LANGUAGES: str = os.getenv("OCR_LANGUAGES", "eng")

    # Anomaly thresholds (configurable per Section 2, Stage 3) ---
    MAX_TERMINATION_NOTICE_DAYS_LOW: int = int(os.getenv("MIN_TERMINATION_NOTICE_DAYS", "15"))
    MAX_PAYMENT_TERMS_DAYS: int = int(os.getenv("MAX_PAYMENT_TERMS_DAYS", "90"))
    YOY_CHANGE_THRESHOLD_PCT: float = float(os.getenv("YOY_CHANGE_THRESHOLD_PCT", "35.0"))
    # Configurable financial "normal" ranges used by Stage 3. The JSON shape is
    # {"ratio_name": [minimum, maximum]}. This keeps industry assumptions out
    # of the code and lets a deployment tune them without rebuilding.
    INDUSTRY_RATIO_RANGES: dict = json.loads(os.getenv(
        "INDUSTRY_RATIO_RANGES_JSON",
        '{"debt_to_assets":[0.0,0.85],"net_margin":[-0.25,0.50]}'
    ))


    # CRM sync
    CRM_PROVIDER: str = os.getenv("CRM_PROVIDER", "notion")  # "notion" | "airtable"
    NOTION_API_KEY: str = os.getenv("NOTION_API_KEY", "")
    NOTION_DATABASE_ID: str = os.getenv("NOTION_DATABASE_ID", "")
    AIRTABLE_API_KEY: str = os.getenv("AIRTABLE_API_KEY", "")
    AIRTABLE_BASE_ID: str = os.getenv("AIRTABLE_BASE_ID", "")
    AIRTABLE_TABLE_NAME: str = os.getenv("AIRTABLE_TABLE_NAME", "Documents")

    # Model memory management
    # See README "Memory Management Strategy" for why these exist.
    MODEL_IDLE_UNLOAD_SECONDS: int = int(os.getenv("MODEL_IDLE_UNLOAD_SECONDS", "120"))
    MAX_CONCURRENT_MODELS: int = int(os.getenv("MAX_CONCURRENT_MODELS", "1"))

    # CORS 
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    PUBLIC_APP_URL: str = os.getenv("PUBLIC_APP_URL", FRONTEND_ORIGIN)


settings = Settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
