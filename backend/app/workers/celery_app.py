"""workers/celery_app.py — Celery application factory."""
from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "privacy_shield",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    # ── Serialisation ─────────────────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # ── Timezone ──────────────────────────────────────────────────────────────
    timezone="UTC",
    enable_utc=True,
    # ── Result backend ────────────────────────────────────────────────────────
    result_expires=86400,        # 24 hours
    result_backend_transport_options={"master_name": "mymaster"},
    # ── Task behaviour ────────────────────────────────────────────────────────
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,   # Fair dispatch for long-running tasks
    # ── Rate limiting ─────────────────────────────────────────────────────────
    task_annotations={
        "tasks.run_scan": {"rate_limit": "20/m"},
        "tasks.process_removal": {"rate_limit": "30/m"},
    },
    # ── Beat schedule (periodic tasks) ────────────────────────────────────────
    beat_schedule={
        "weekly-rescan": {
            "task": "tasks.scheduled_rescan",
            "schedule": crontab(hour=2, minute=0, day_of_week="monday"),  # Every Monday 2am UTC
        },
    },
    # ── Monitoring ────────────────────────────────────────────────────────────
    worker_send_task_events=True,
    task_send_sent_event=True,
)
