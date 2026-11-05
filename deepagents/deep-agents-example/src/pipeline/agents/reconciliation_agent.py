"""
Agent 3: Reconciliation Engine Agent
File: src/pipeline/agents/reconciliation_agent.py

Cross-references actual transactions against expected ledger obligations,
computes variances, and tags each transaction with an audit match status.
"""

import sqlite3
from typing import List, Optional
from langchain_core.messages import HumanMessage
from src.pipeline.db import get_db_path
from src.pipeline.schemas import AgentState, ReconciliationRecord


class ReconciliationAgent:
    """
    Agent 3: Matches actual transactions against expected ledger commitments,
    calculating numeric variance and setting status (EXACT_MATCH, AMOUNT_MISMATCH, UNMATCHED).
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path

    @property
    def db_path(self) -> str:
        return get_db_path(self._db_path)

    def fetch_expected_invoices(self) -> List[tuple]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT expected_id, party_name, expected_amount, currency FROM expected_invoices;")
            return cursor.fetchall()

    def reconcile_transaction(self, tx: dict, expected_records: List[tuple]) -> ReconciliationRecord:
        tx_desc = tx["description"].upper()
        tx_amt = tx["amount"]

        for exp_id, party, exp_amt, exp_curr in expected_records:
            keywords = [w for w in party.upper().split() if len(w) > 3]
            if not keywords:
                keywords = [w for w in party.upper().split() if len(w) >= 3] or [party.upper()]

            if any(kw in tx_desc for kw in keywords):
                variance = round(tx_amt - exp_amt, 2)
                status = "EXACT_MATCH" if abs(variance) < 0.01 else "AMOUNT_MISMATCH"
                notes = (
                    f"Exact match with {exp_id} ({party})"
                    if status == "EXACT_MATCH"
                    else f"Partial match with {exp_id}. Variance: {variance} {tx.get('currency', 'CHF')}"
                )
                return ReconciliationRecord(
                    transaction_id=tx["transaction_id"],
                    expected_id=exp_id,
                    status=status,
                    variance=variance,
                    notes=notes,
                )

        return ReconciliationRecord(
            transaction_id=tx["transaction_id"],
            expected_id=None,
            status="UNMATCHED",
            variance=0.0,
            notes="No matching expected invoice found in ledger",
        )

    def run(self, state: AgentState) -> dict:
        txs = state.get("transactions", [])
        if not txs:
            return {
                "reconciliation_results": [],
                "messages": [HumanMessage(content="ReconciliationAgent: No records to reconcile.")],
            }

        expected_records = self.fetch_expected_invoices()
        recon_results = [
            self.reconcile_transaction(tx, expected_records).model_dump()
            for tx in txs
        ]

        exact_c = sum(1 for r in recon_results if r["status"] == "EXACT_MATCH")
        mismatch_c = sum(1 for r in recon_results if r["status"] == "AMOUNT_MISMATCH")
        unmatched_c = sum(1 for r in recon_results if r["status"] == "UNMATCHED")

        summary = (
            f"ReconciliationAgent: Processed {len(recon_results)} items. "
            f"Exact: {exact_c}, Mismatch: {mismatch_c}, Unmatched: {unmatched_c}."
        )
        return {"reconciliation_results": recon_results, "messages": [HumanMessage(content=summary)]}


def reconciliation_agent_node(state: AgentState) -> dict:
    """LangGraph node function for ReconciliationAgent."""
    agent = ReconciliationAgent()
    return agent.run(state)

