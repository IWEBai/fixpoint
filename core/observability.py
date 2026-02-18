"""
Observability utilities for Fixpoint.
Structured logging and correlation IDs for debugging.
"""
from __future__ import annotations

import logging
import json
import os
from datetime import datetime, timezone
import uuid
from typing import Optional, Dict, Any

# Configure structured logging with correlation ID support
class CorrelationIDFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = getattr(logging, '_correlation_id', 'no-id')
        return True

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(correlation_id)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Add correlation ID filter
for handler in logging.root.handlers:
    handler.addFilter(CorrelationIDFilter())

logger = logging.getLogger(__name__)


class CorrelationContext:
    """Context manager for correlation IDs."""
    
    def __init__(self, correlation_id: Optional[str] = None):
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.old_id = None
    
    def __enter__(self):
        # Store old correlation ID if any
        self.old_id = getattr(logging, '_correlation_id', None)
        logging._correlation_id = self.correlation_id
        return self
    
    def __exit__(self, *args):
        # Restore old correlation ID
        if self.old_id:
            logging._correlation_id = self.old_id
        else:
            delattr(logging, '_correlation_id')


_REDACT_KEYS = {
    "token",
    "access_token",
    "github_token",
    "authorization",
    "secret",
    "webhook_secret",
    "private_key",
    "password",
}


def _redact(obj: Any) -> Any:
    """Best-effort redaction for audit metadata."""
    try:
        if isinstance(obj, dict):
            redacted: dict[str, Any] = {}
            for k, v in obj.items():
                key = str(k).lower()
                if key in _REDACT_KEYS or any(s in key for s in ("token", "secret", "password", "authorization")):
                    redacted[k] = "[REDACTED]"
                else:
                    redacted[k] = _redact(v)
            return redacted
        if isinstance(obj, list):
            return [_redact(v) for v in obj]
        if isinstance(obj, tuple):
            return tuple(_redact(v) for v in obj)
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        # Fallback: make JSON-safe
        return str(obj)
    except Exception:
        return "[UNSERIALIZABLE]"


def log_audit_event(
    action: str,
    result: str,
    *,
    correlation_id: Optional[str] = None,
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Emit a structured audit log entry.

    - Always writes a JSON line to logs.
    - Optionally persists to SQLite if FIXPOINT_AUDIT_LOG_DB=true.
    """
    ts = datetime.now(timezone.utc).isoformat()
    cid = correlation_id or getattr(logging, "_correlation_id", "no-id")

    event = {
        "type": "audit",
        "timestamp": ts,
        "correlation_id": cid,
        "action": str(action),
        "result": str(result),
        "repo": repo,
        "pr_number": pr_number,
        "metadata": _redact(metadata or {}),
    }

    # Emit as a single JSON line (works with most log shippers)
    with CorrelationContext(cid):
        logger.info(json.dumps(event, ensure_ascii=False, sort_keys=True))

    # Optional DB persistence (best-effort)
    if os.getenv("FIXPOINT_AUDIT_LOG_DB", "").lower() in ("1", "true", "yes"):
        try:
            from core.db import insert_audit_log

            insert_audit_log(
                action=str(action),
                timestamp=ts,
                correlation_id=cid,
                repo=repo,
                pr_number=pr_number,
                result=str(result),
                metadata_json=json.dumps(event.get("metadata", {}), ensure_ascii=False, sort_keys=True),
            )
        except Exception:
            # Never break runtime due to audit persistence
            pass


def log_webhook_event(
    event_type: str,
    action: str,
    owner: str,
    repo: str,
    pr_number: Optional[int] = None,
    correlation_id: Optional[str] = None,
) -> str:
    """
    Log webhook event with structured data.
    
    Returns:
        Correlation ID for this event
    """
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
    
    with CorrelationContext(correlation_id):
        logger.info(
            "Webhook event received",
            extra={
                "event_type": event_type,
                "action": action,
                "owner": owner,
                "repo": repo,
                "pr_number": pr_number,
            }
        )

    # Audit trail (structured)
    repo_full = f"{owner}/{repo}" if owner and repo else None
    log_audit_event(
        action="webhook_event",
        result="received",
        correlation_id=correlation_id,
        repo=repo_full,
        pr_number=pr_number,
        metadata={
            "event_type": event_type,
            "action": action,
        },
    )
    
    return correlation_id


def log_processing_result(
    correlation_id: str,
    status: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Log processing result with structured data."""
    with CorrelationContext(correlation_id):
        log_data = {
            "status": status,
            "message": message,
        }
        if metadata:
            log_data.update(metadata)
        
        if status == "error":
            logger.error(f"Processing failed: {message}", extra=log_data)
        elif status == "success":
            logger.info(f"Processing succeeded: {message}", extra=log_data)
        else:
            logger.info(f"Processing: {message}", extra=log_data)

    # Audit trail (structured)
    log_audit_event(
        action="processing_result",
        result=str(status),
        correlation_id=correlation_id,
        repo=log_data.get("repo"),
        pr_number=log_data.get("pr_number"),
        metadata={"message": message, **(metadata or {})},
    )


def log_fix_applied(
    correlation_id: str,
    pr_number: int,
    files_fixed: list[str],
    findings_count: int,
):
    """Log when fixes are applied."""
    with CorrelationContext(correlation_id):
        logger.info(
            f"Fixes applied to PR #{pr_number}",
            extra={
                "pr_number": pr_number,
                "files_fixed": files_fixed,
                "findings_count": findings_count,
            }
        )

    # Audit trail (structured)
    log_audit_event(
        action="fix_applied",
        result="success",
        correlation_id=correlation_id,
        pr_number=pr_number,
        metadata={
            "files_fixed": files_fixed,
            "findings_count": findings_count,
        },
    )
