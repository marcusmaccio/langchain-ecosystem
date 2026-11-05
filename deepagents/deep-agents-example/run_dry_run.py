#!/usr/bin/env python3
"""
Use Case 3: Offline / Deterministic Dry-Run Pipeline
Mocks the Reader Agent LLM output with realistic Swiss banking transactions.
Executes all subsequent agents (Storage -> Reconciliation -> Reporting -> Dispatch)
in <1 second without requiring LM Studio or external network calls.
"""

import os
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage

from main import create_demo_feed
from src.pipeline.db import init_database
from src.pipeline.harness import build_financial_pipeline

MOCK_EXTRACTED_JSON = """{
  "items": [
    {
      "transaction_id": "CH-TX-001",
      "date": "2026-10-28",
      "description": "SUNRISE COMMUNICATIONS AG LAUSANNE",
      "amount": -89.90,
      "currency": "CHF"
    },
    {
      "transaction_id": "CH-TX-002",
      "date": "2026-10-29",
      "description": "LOYER APPARTEMENT DUPLEX 1ER ETAGE",
      "amount": 2150.00,
      "currency": "CHF"
    },
    {
      "transaction_id": "CH-TX-003",
      "date": "2026-11-01",
      "description": "SERVICES INDUSTRIELS DE GENEVE (SIG)",
      "amount": -145.20,
      "currency": "CHF"
    },
    {
      "transaction_id": "CH-TX-004",
      "date": "2026-11-02",
      "description": "UNEXPECTED CAFE RESTAURANT",
      "amount": -24.50,
      "currency": "CHF"
    }
  ]
}"""


def main():
    print("=" * 65)
    print("  RUNNING DETERMINISTIC DRY-RUN (OFFLINE DEMO)")
    print("=" * 65)

    input_file = create_demo_feed()
    init_database()

    mock_llm_client = MagicMock()
    mock_llm_client.invoke.return_value = AIMessage(content=MOCK_EXTRACTED_JSON)

    mock_webhook = MagicMock()
    mock_webhook.raise_for_status.return_value = None

    with patch("src.pipeline.agents.reader_agent.get_resilient_lm_studio_client", return_value=mock_llm_client):
        with patch("requests.post", return_value=mock_webhook):
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

    print("\n--- AGENT AUDIT LOG ---")
    for msg in output["messages"]:
        print(f"[{msg.type.upper()}] {msg.content}")

    print("\n--- RECONCILIATION AUDIT ---")
    for r in output.get("reconciliation_results", []):
        print(f"• [{r['status']:15}] TX: {r['transaction_id']:10} | Exp: {str(r.get('expected_id')):12} | Variance: {r.get('variance', 0.0):+7.2f} CHF | {r.get('notes')}")

    print("\n--- STATE SUMMARY ---")
    print(f"DB Status:       {output.get('db_status')}")
    print(f"Report File:     {output.get('report_path')}")
    print(f"Dispatch Status: {output.get('dispatch_status')}")
    print("=" * 65)


if __name__ == "__main__":
    main()

