import argparse
import os
import sys
from src.pipeline.db import init_database
from src.pipeline.harness import build_financial_pipeline


def run_pipeline(file_path: str):
    """Executes the financial pipeline on the given input file."""
    init_database()

    initial_input = {
        "raw_file_path": file_path,
        "transactions": [],
        "reconciliation_results": [],
        "db_status": "PENDING",
        "report_path": None,
        "dispatch_status": "PENDING",
        "messages": [],
    }

    pipeline = build_financial_pipeline()
    final_output = pipeline.invoke(initial_input)

    print("\n================== PIPELINE AUDIT LOG ==================")
    for message in final_output["messages"]:
        msg_type = getattr(message, "type", "MESSAGE").upper()
        print(f"[{msg_type}] {message.content}")

    print("\n================== FINAL STATE SUMMARY =================")
    print(f"DB Status:       {final_output.get('db_status')}")
    print(f"Report File:     {final_output.get('report_path')}")
    print(f"Dispatch Status: {final_output.get('dispatch_status')}")
    return final_output


def create_demo_feed(sample_csv: str = "test_feed.csv") -> str:
    with open(sample_csv, "w", encoding="utf-8") as f:
        f.write("28.10.2026;SUNRISE COMMUNICATIONS AG LAUSANNE;-89.90;CH-TX-001\n")
        f.write("29.10.2026;LOYER APPARTEMENT DUPLEX 1ER ETAGE;2'150.00;CH-TX-002\n")
        f.write("01.11.2026;SERVICES INDUSTRIELS DE GENEVE (SIG);-145.20;CH-TX-003\n")
        f.write("02.11.2026;UNEXPECTED CAFE RESTAURANT;-24.50;CH-TX-004\n")
    return sample_csv


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Local Multi-Agent Financial Ingestion, Reconciliation & Dispatch Pipeline"
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        help="Path to statement file (.csv or .pdf). If omitted, generates test_feed.csv demo.",
    )
    args = parser.parse_args()

    input_file = args.file or create_demo_feed()
    run_pipeline(input_file)

