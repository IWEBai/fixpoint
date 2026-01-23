"""
Generate email report from AuditShield metrics.
Simple text report for email distribution.
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.metrics import generate_email_report, generate_metrics_summary


def main():
    report = generate_email_report()
    summary = generate_metrics_summary()
    
    if not summary:
        print("No metrics collected yet.")
        return
    
    # Add timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    full_report = f"AuditShield Metrics Report\n"
    full_report += f"Generated: {timestamp}\n"
    full_report += "=" * 50 + "\n\n"
    full_report += report
    
    # Print to console
    print(full_report)
    
    # Also save to file
    output_path = Path("auditshield_report.txt")
    output_path.write_text(full_report, encoding="utf-8")
    print(f"\n✅ Report saved to: {output_path}")


if __name__ == "__main__":
    main()
