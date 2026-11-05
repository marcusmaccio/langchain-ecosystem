#!/usr/bin/env python3
"""
Use Case 1: Core 3-Agent Financial Pipeline
Runs Agent 1 (Reader) -> Agent 2 (Storage) -> Agent 3 (Reconciliation).
Omits reporting and dispatch notifications.
"""

import argparse
from main import create_demo_feed
from src.pipeline.db import init_database
from src.pipeline.harness import build_core_financial_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Run Core 3-Agent Pipeline (Reader -> Storage -> Reconciliation)"
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        help="Path to statement file (.csv or .pdf). Defaults to demo feed.",
    )
    args = parser.parse_args()

    input_file = args.file or create_demo_feed()
    init_database()

    print("=" * 65)
    print("  RUNNING CORE 3-AGENT PIPELINE")
    print(f"  Input File: {input_file}")
    print("=" * 65)

    pipeline = build_core_financial_pipeline()
    output = pipeline.invoke({
        "raw_file_path": input_file,
        "transactions": [],
        "reconciliation_results": [],
        "db_status": "PENDING",
        "report_path": None,
        "dispatch_status": "SKIPPED",
        "messages": [],
    })

    print("\n--- AGENT AUDIT MESSAGES ---")
    for msg in output["messages"]:
        msg_type = getattr(msg, "type", "MESSAGE").upper()
        print(f"[{msg_type}] {msg.content}")

    print("\n--- RECONCILIATION SUMMARY ---")
    recon_results = output.get("reconciliation_results", [])
    if not recon_results:
        print("No reconciliation records generated.")
    else:
        for r in recon_results:
            tx_id = r.get("transaction_id")
            status = r.get("status")
            exp_id = r.get("expected_id") or "NONE"
            variance = r.get("variance", 0.0)
            notes = r.get("notes", "")
            print(f"• [{status:15}] TX: {tx_id:10} | Exp: {exp_id:12} | Variance: {variance:+7.2f} | {notes}")

    print("\n--- STATE SUMMARY ---")
    print(f"Database Status:        {output.get('db_status')}")
    print(f"Transactions Processed: {len(output.get('transactions', []))}")
    print(f"Reconciled Items:       {len(recon_results)}")
    print("=" * 65)


if __name__ == "__main__":
    main()
