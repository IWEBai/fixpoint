"""
Metrics collection for AuditShield.
Logs metrics, exports CSV, generates email reports.
NO DASHBOARD - Data > Dashboards (early-stage).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional
from collections import defaultdict

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
    
    return {
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


def generate_email_report() -> str:
    """
    Generate email report text from metrics.
    
    Returns:
        Email report as text
    """
    summary = generate_metrics_summary()
    
    if not summary:
        return "No metrics collected yet."
    
    report = "AuditShield Metrics Report\n"
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
