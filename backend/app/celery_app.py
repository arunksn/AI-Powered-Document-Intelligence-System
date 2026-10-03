from celery import Celery
from app.config import settings

celery_app = Celery(
    "docintel",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Each document's 5 stages must run in order -> one task chains into
    # the next explicitly (see tasks.py) rather than relying on Celery
    # concurrency, which would let stages race each other for the same doc.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    # Keep worker concurrency modest so we don't blow the Railway memory
    # envelope with multiple CPU-bound ML stages running in parallel.
    worker_concurrency=int(__import__("os").getenv("CELERY_CONCURRENCY", "2")),
)

import celery.app.trace
celery.app.trace.setup_worker_optimizations = lambda *args, **kwargs: None
celery.app.trace.reset_worker_optimizations(celery_app)