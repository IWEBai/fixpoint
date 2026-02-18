"""
Metrics collection for Fixpoint.
Logs metrics, exports CSV, generates email reports.
NO DASHBOARD - Data > Dashboards (early-stage).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Iterable

from core.observability import log_processing_result


# In-memory metrics store (in production, use database)
_metrics_store: List[Dict] = []


def record_metric(
    event_type: str,
    repo: str,
    pr_number: Optional[int] = None,
    violations_found: int = 0,
    violations_fixed: int = 0,
    mode: str = "warn",
    status: str = "success",
    metadata: Optional[Dict] = None,
    installation_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """
    Record a metric event.
    
    Args:
        event_type: Type of event (e.g., "pr_processed", "fix_applied")
        repo: Repository name (owner/repo)
        pr_number: PR number if applicable
        violations_found: Number of violations found
        violations_fixed: Number of violations fixed
        mode: "warn" or "enforce"
        status: "success", "failure", "warn_mode", etc.
        metadata: Additional metadata dict
    """
    metric = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "repo": repo,
        "pr_number": pr_number,
        "violations_found": violations_found,
        "violations_fixed": violations_fixed,
        "mode": mode,
        "status": status,
        "metadata": metadata or {},
    }
    
    _metrics_store.append(metric)
    
    # Persist to DB for dashboard (when installation_id available)
    if installation_id is not None:
        try:
            from core.db import insert_run
            insert_run(
                installation_id=installation_id,
                repo=repo,
                status=status,
                pr_number=pr_number,
                violations_found=violations_found,
                violations_fixed=violations_fixed,
                correlation_id=correlation_id,
            )
        except Exception as e:
            log_processing_result("metrics", "db_error", f"Failed to persist run: {e}")
    
    # Also log for observability
    log_processing_result(
        "metrics",
        status,
        f"Metric recorded: {event_type}",
        metric,
    )


def export_metrics_csv(output_path: Path) -> bool:
    """
    Export metrics to CSV file.
    
    Args:
        output_path: Path to write CSV file
    
    Returns:
        True if successful
    """
    if not _metrics_store:
        return False
    
    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            if not _metrics_store:
                return False
            
            fieldnames = list(_metrics_store[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for metric in _metrics_store:
                # Flatten metadata dict for CSV
                row = metric.copy()
                if row.get("metadata"):
                    row["metadata"] = json.dumps(row["metadata"])
                writer.writerow(row)
        
        return True
    except Exception as e:
        print(f"Error exporting metrics to CSV: {e}")
        return False


def generate_metrics_summary() -> Dict:
    """
    Generate summary statistics from metrics.
    
    Returns:
        Dict with summary statistics
    """
    if not _metrics_store:
        return {}
    
    total_events = len(_metrics_store)
    repos = set(m.get("repo") for m in _metrics_store)
    prs_processed = len([m for m in _metrics_store if m.get("event_type") == "pr_processed"])
    fixes_applied = len([m for m in _metrics_store if m.get("event_type") == "fix_applied"])
    
    total_violations_found = sum(m.get("violations_found", 0) for m in _metrics_store)
    total_violations_fixed = sum(m.get("violations_fixed", 0) for m in _metrics_store)
    
    warn_mode_count = len([m for m in _metrics_store if m.get("mode") == "warn"])
    enforce_mode_count = len([m for m in _metrics_store if m.get("mode") == "enforce"])
    
    success_count = len([m for m in _metrics_store if m.get("status") == "success"])
    failure_count = len([m for m in _metrics_store if m.get("status") == "failure"])
    
    run_summary = summarize_run_metrics(_metrics_store)

    summary = {
        "total_events": total_events,
        "unique_repos": len(repos),
        "prs_processed": prs_processed,
        "fixes_applied": fixes_applied,
        "total_violations_found": total_violations_found,
        "total_violations_fixed": total_violations_fixed,
        "fix_rate": total_violations_fixed / total_violations_found if total_violations_found > 0 else 0,
        "warn_mode_events": warn_mode_count,
        "enforce_mode_events": enforce_mode_count,
        "success_rate": success_count / total_events if total_events > 0 else 0,
        "failure_count": failure_count,
    }

    summary.update(run_summary)
    return summary


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (percentile / 100.0)
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)
    if f == c:
        return float(values_sorted[f])
    return float(values_sorted[f] + (values_sorted[c] - values_sorted[f]) * (k - f))


def _iter_run_metrics(metrics: Iterable[Dict]) -> list[Dict]:
    return [m for m in metrics if m.get("event_type") == "run_completed"]


def summarize_run_metrics(metrics: Iterable[Dict]) -> Dict:
    runs = _iter_run_metrics(metrics)
    runtimes = [
        float(m.get("metadata", {}).get("runtime_seconds", 0) or 0)
        for m in runs
        if (m.get("metadata") or {}).get("runtime_seconds") is not None
    ]
    fixes_attempted = sum(int((m.get("metadata") or {}).get("fixes_attempted", 0) or 0) for m in runs)
    fixes_applied = sum(int((m.get("metadata") or {}).get("fixes_applied", 0) or 0) for m in runs)

    degraded_count = 0
    degraded_reasons: Dict[str, int] = {}
    failure_reasons: Dict[str, int] = {}

    for m in runs:
        md = m.get("metadata", {}) or {}
        reasons = md.get("degraded_reasons") or []
        if reasons:
            degraded_count += 1
            for r in reasons:
                key = str(r)
                degraded_reasons[key] = degraded_reasons.get(key, 0) + 1
        failure_reason = md.get("failure_reason")
        if failure_reason:
            key = str(failure_reason)
            failure_reasons[key] = failure_reasons.get(key, 0) + 1

    return {
        "run_count": len(runs),
        "runtime_p50": _percentile(runtimes, 50),
        "runtime_p95": _percentile(runtimes, 95),
        "fixes_attempted": fixes_attempted,
        "fixes_applied": fixes_applied,
        "degraded_to_warn_count": degraded_count,
        "degraded_reasons": degraded_reasons,
        "failure_reasons": failure_reasons,
    }


def generate_email_report() -> str:
    """
    Generate email report text from metrics.
    
    Returns:
        Email report as text
    """
    summary = generate_metrics_summary()
    
    if not summary:
        return "No metrics collected yet."
    
    report = "Fixpoint Metrics Report\n"
    report += "=" * 50 + "\n\n"
    
    report += f"Total Events: {summary['total_events']}\n"
    report += f"Unique Repos: {summary['unique_repos']}\n"
    report += f"PRs Processed: {summary['prs_processed']}\n"
    report += f"Fixes Applied: {summary['fixes_applied']}\n\n"
    
    report += "Violations:\n"
    report += f"  Found: {summary['total_violations_found']}\n"
    report += f"  Fixed: {summary['total_violations_fixed']}\n"
    report += f"  Fix Rate: {summary['fix_rate']:.1%}\n\n"
    
    report += "Mode Distribution:\n"
    report += f"  Warn Mode: {summary['warn_mode_events']}\n"
    report += f"  Enforce Mode: {summary['enforce_mode_events']}\n\n"
    
    report += f"Success Rate: {summary['success_rate']:.1%}\n"
    report += f"Failures: {summary['failure_count']}\n"
    
    return report


def clear_metrics():
    """Clear metrics store (for testing)."""
    global _metrics_store
    _metrics_store.clear()
