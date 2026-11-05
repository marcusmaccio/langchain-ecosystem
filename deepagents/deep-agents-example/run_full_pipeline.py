#!/usr/bin/env python3
"""
Use Case 2: Full 5-Agent Financial Pipeline
Runs Reader -> Storage -> Reconciliation -> Reporting -> Dispatch.
"""

import argparse
import os

from main import create_demo_feed
from src.pipeline.db import init_database
from src.pipeline.harness import build_financial_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Run Full 5-Agent Pipeline (Ingestion, Storage, Reconciliation, Reporting, Dispatch)"
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        help="Path to statement file (.csv or .pdf). Defaults to demo feed.",
    )
    parser.add_argument(
        "--channel",
        "-c",
        type=str,
        choices=["webhook", "smtp"],
        default=os.getenv("DISPATCH_CHANNEL", "webhook"),
        help="Dispatch notification channel (webhook or smtp). Default: webhook",
    )
    args = parser.parse_args()

    os.environ["DISPATCH_CHANNEL"] = args.channel
    input_file = args.file or create_demo_feed()
    init_database()

    print("=" * 65)
    print("  RUNNING FULL 5-AGENT PIPELINE")
    print(f"  Input File:       {input_file}")
    print(f"  Dispatch Channel: {args.channel}")
    print("=" * 65)

    pipeline = build_financial_pipeline()
    output = pipeline.invoke({
        "raw_file_path": input_file,
        "transactions": [],
        "reconciliation_results": [],
        "db_status": "PENDING",
        "report_path": None,
        "dispatch_status": "PENDING",
        "messages": [],
    })

    print("\n--- AGENT AUDIT MESSAGES ---")
    for msg in output["messages"]:
        msg_type = getattr(msg, "type", "MESSAGE").upper()
        print(f"[{msg_type}] {msg.content}")

    print("\n--- PIPELINE EXECUTION SUMMARY ---")
    print(f"Database Status:     {output.get('db_status')}")
    print(f"Ingested Records:    {len(output.get('transactions', []))}")
    print(f"Reconciled Records:  {len(output.get('reconciliation_results', []))}")
    print(f"Generated Report:    {output.get('report_path')}")
    print(f"Dispatch Status:     {output.get('dispatch_status')}")
    print("=" * 65)


if __name__ == "__main__":
    main()

