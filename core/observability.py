"""
Observability utilities for AuditShield.
Structured logging and correlation IDs for debugging.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
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
            f"Webhook event received",
            extra={
                "event_type": event_type,
                "action": action,
                "owner": owner,
                "repo": repo,
                "pr_number": pr_number,
            }
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
