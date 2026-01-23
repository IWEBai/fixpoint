"""
Export AuditShield metrics to CSV.
Simple script to generate data exports for analysis.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.metrics import export_metrics_csv, generate_metrics_summary, generate_email_report


def main():
    output_path = Path("auditshield_metrics.csv")
    
    print("Exporting AuditShield metrics...")
    
    if export_metrics_csv(output_path):
        print(f"✅ Metrics exported to: {output_path}")
        
        # Show summary
        summary = generate_metrics_summary()
        if summary:
            print("\nSummary:")
            print(f"  Total Events: {summary['total_events']}")
            print(f"  Unique Repos: {summary['unique_repos']}")
            print(f"  PRs Processed: {summary['prs_processed']}")
            print(f"  Fixes Applied: {summary['fixes_applied']}")
            print(f"  Violations Found: {summary['total_violations_found']}")
            print(f"  Violations Fixed: {summary['total_violations_fixed']}")
            print(f"  Fix Rate: {summary['fix_rate']:.1%}")
            print(f"  Success Rate: {summary['success_rate']:.1%}")
    else:
        print("❌ No metrics to export or export failed.")


if __name__ == "__main__":
    main()
