"""
Notification helpers for Railo.

Sends Slack webhook messages and/or email when notable events occur
(fix applied, CI passed/failed).  Each installation can configure its
own destinations in the ``notification_settings`` table.

Defaults are ALL OFF — users must explicitly enable events.

Per-repo, per-event throttle: max ``RAILO_NOTIF_THROTTLE`` (default 5)
notifications per hour.  When ``digest_mode`` is enabled the worker does
not send individually — a separate daily /api/notifications/digest endpoint
flushes the queue.

Environment variables (for email via SMTP):
    SMTP_HOST         – SMTP server hostname  (default: localhost)
    SMTP_PORT         – SMTP server port      (default: 587)
    SMTP_USER         – Login username        (optional)
    SMTP_PASSWORD     – Login password        (optional)
    SMTP_FROM         – Sender address        (default: railo@localhost)
    SMTP_USE_TLS      – "1" / "true" to STARTTLS  (default: 1)
    RAILO_NOTIF_THROTTLE – max events/repo/hour (default 5)
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from .db import (
    get_notification_settings,
    is_notification_throttled,
    log_notification_sent,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event → human-readable label mapping
# ---------------------------------------------------------------------------

_EVENT_LABELS: dict[str, str] = {
    "fix_applied":  "Fix PR created",
    "ci_success":   "CI checks passed",
    "ci_failure":   "CI checks failed — revert applied",
    "ci_timeout":   "CI monitor timed out",
}

# Which DB flag gates each event type (all default OFF)
_EVENT_GATE: dict[str, str] = {
    "fix_applied":      "notify_on_fix_applied",
    "ci_success":       "notify_on_ci_success",
    "ci_failure":       "notify_on_ci_failure",
    "ci_timeout":       "notify_on_ci_failure",  # treat timeout like failure
    "revert_triggered": "notify_on_revert",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_notification(
    event: str,
    data: dict,
    installation_id: Optional[int],
) -> None:
    """
    Dispatch a notification for *event* to all configured channels.

    This is a best-effort fire-and-forget — exceptions are logged but never
    propagated to the caller.

    Notifications are:
    - Default OFF (users must opt in per-event)
    - Throttled at max RAILO_NOTIF_THROTTLE per repo per hour
    - Skipped if digest_mode is on (flushed by the daily digest endpoint)
    - Always include correlation_id and run_link when present

    Args:
        event:           One of the keys in ``_EVENT_LABELS``.
        data:            Arbitrary dict with context (repo, pr_url, …).
        installation_id: The GitHub App installation to look up settings for.
    """
    try:
        _dispatch(event, data, installation_id)
    except Exception:
        logger.exception("send_notification: unhandled error for event=%s", event)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dispatch(event: str, data: dict, installation_id: Optional[int]) -> None:
    settings = None
    if installation_id:
        settings = get_notification_settings(installation_id)

    gate_flag = _EVENT_GATE.get(event, "notify_on_fix_applied")
    label = _EVENT_LABELS.get(event, event)

    # Gate: user must explicitly opt in (default 0 = OFF)
    is_opted_in = bool((settings or {}).get(gate_flag, 0))
    if not is_opted_in:
        return

    # Digest mode: log to queue, do not send immediately
    if (settings or {}).get("digest_mode", 0):
        if installation_id:
            try:
                log_notification_sent(
                    installation_id,
                    data.get("repo", ""),
                    event,
                )
            except Exception:
                pass
        return

    repo = data.get("repo", "")

    # Throttle check: max N per repo per hour
    if installation_id and is_notification_throttled(installation_id, repo, event):
        logger.debug(
            "Notification throttled: install=%s repo=%s event=%s",
            installation_id, repo, event,
        )
        return

    # Build body (always include correlation_id and run_link when present)
    pr_url = data.get("pr_url") or data.get("fix_pr_url", "")
    extra = data.get("message", "")
    correlation_id = data.get("correlation_id", "")
    run_link = data.get("run_link", "")

    body = f"*[Railo]* {label}"
    if repo:
        body += f"\nRepo: `{repo}`"
    if pr_url:
        body += f"\nPR: {pr_url}"
    if run_link:
        body += f"\nRun: {run_link}"
    if correlation_id:
        body += f"\nCorrelation ID: `{correlation_id}`"
    if extra:
        body += f"\n{extra}"

    # --- Slack ---
    slack_url = (settings or {}).get("slack_webhook_url") or os.getenv("SLACK_WEBHOOK_URL", "")
    if slack_url:
        _send_slack(slack_url, body)

    # --- Email ---
    email_to = (settings or {}).get("email") or os.getenv("SMTP_TO", "")
    if email_to:
        subject = f"[Railo] {label}" + (f" — {repo}" if repo else "")
        plain_body = body.replace("*", "").replace("`", "")
        _send_email(email_to, subject, plain_body)

    # Record for throttle tracking
    if installation_id and (slack_url or email_to):
        try:
            log_notification_sent(installation_id, repo, event)
        except Exception:
            pass


def _dispatch_digest(installation_id: int, events: list) -> None:
    """Send a batched digest summary for *installation_id*.

    *events* is the list returned by ``get_pending_digest_events()``.
    Sends via Slack and/or email if configured; silently skips if neither
    destination is set up.
    """
    settings = get_notification_settings(installation_id)
    if not settings:
        return

    if not events:
        return

    lines = [f"*[Railo] Daily digest \u2014 {len(events)} event type(s)*"]
    for e in events:
        lines.append(
            f"\u2022 {e['repo']} \u2014 {e['event']} \u00d7 {e['cnt']}"
            f" (last: {str(e.get('last_at', ''))[:10]})"
        )
    body = "\n".join(lines)

    slack_url = settings.get("slack_webhook_url") or os.getenv("SLACK_WEBHOOK_URL", "")
    if slack_url:
        _send_slack(slack_url, body)

    email_to = settings.get("email") or os.getenv("SMTP_TO", "")
    if email_to:
        _send_email(
            email_to,
            "[Railo] Daily activity digest",
            body.replace("*", "").replace("`", ""),
        )


def _send_slack(webhook_url: str, text: str) -> None:
    """POST a JSON payload to a Slack incoming webhook URL."""
    payload = json.dumps({"text": text}).encode()
    req = Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                logger.warning("Slack webhook returned HTTP %s", resp.status)
    except URLError as exc:
        logger.warning("Slack webhook error: %s", exc)


def _send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email via SMTP."""
    smtp_host = os.getenv("SMTP_HOST", "localhost")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", "railo@localhost")
    use_tls = os.getenv("SMTP_USE_TLS", "1").lower() not in {"0", "false", "no"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls()
            if smtp_user and smtp_password:
                smtp.login(smtp_user, smtp_password)
            smtp.sendmail(smtp_from, [to], msg.as_string())
    except Exception as exc:
        logger.warning("Email send error: %s", exc)
