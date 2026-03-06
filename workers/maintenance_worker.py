"""Periodic maintenance tasks — safe to enqueue as an RQ job or invoke via Flask CLI.

Scheduled job (RQ example):
    from workers.maintenance_worker import run_maintenance
    queues["low"].enqueue(run_maintenance)

Cron example (daily at 02:00 AM):
    0 2 * * * cd /app && flask maintenance >> /var/log/railo/maintenance.log 2>&1
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def run_maintenance(
    retention_days: int | None = None,
    delivery_id_ttl_days: int = 30,
) -> dict:
    """Run all periodic housekeeping tasks.

    Tasks performed:
    - Prune run metadata older than *retention_days* (default: ``RUN_RETENTION_DAYS`` env,
      fallback 90 days).  Code is never stored — only metadata rows are removed.
    - Prune delivery-ID dedup records older than *delivery_id_ttl_days* (default 30 days).

    Returns a summary dict suitable for structured logging / RQ job output.
    """
    from core.db import prune_old_runs, prune_old_delivery_ids  # lazy import — safe on Windows

    if retention_days is None:
        retention_days = int(os.getenv("RUN_RETENTION_DAYS", "90"))

    runs_deleted = prune_old_runs(retention_days)
    delivery_ids_deleted = prune_old_delivery_ids(delivery_id_ttl_days)

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "retention_days": retention_days,
        "runs_deleted": runs_deleted,
        "delivery_ids_deleted": delivery_ids_deleted,
    }
    logger.info("Maintenance complete: %s", summary)
    return summary


def run_digest_flush() -> dict:
    """Flush pending notification digest events for all active installations.

    Iterates every installation that has digest_mode enabled, collects queued
    events from ``notification_log``, and sends a single summary message via
    Slack / email.  Safe to call multiple times — events already sent are not
    re-sent.

    Returns a summary dict with per-installation results.
    """
    from core.db import get_connection  # lazy import
    import json as _json

    conn = get_connection()
    try:
        # Find all installations that have digest_mode=1
        cur = conn.execute(
            "SELECT installation_id FROM notification_settings WHERE digest_mode = 1"
        )
        install_ids = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    if not install_ids:
        result = {
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "installations_flushed": 0,
            "details": [],
        }
        logger.info("Digest flush: no digest-mode installations found")
        return result

    details = []
    for install_id in install_ids:
        try:
            from core.db import get_pending_digest_events  # lazy import
            from core.notifications import _dispatch_digest  # lazy import
            events = get_pending_digest_events(install_id)
            if events:
                _dispatch_digest(install_id, events)
            details.append({"installation_id": install_id, "events_flushed": len(events)})
        except Exception as exc:
            logger.error("Digest flush failed for installation %s: %s", install_id, exc)
            details.append({"installation_id": install_id, "error": str(exc)})

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "installations_flushed": len(install_ids),
        "details": details,
    }
    logger.info("Digest flush complete: %s", summary)
    return summary
