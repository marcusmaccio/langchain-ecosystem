"""
Agent 2: Database Storage Agent
File: src/pipeline/agents/storage_agent.py

Idempotently persists clean, normalized transaction records into SQLite.
"""

import sqlite3
from typing import Optional
from langchain_core.messages import HumanMessage
from src.pipeline.db import get_db_path
from src.pipeline.schemas import AgentState


class StorageAgent:
    """
    Agent 2: Handles relational database persistence for normalized financial transactions.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path

    @property
    def db_path(self) -> str:
        return get_db_path(self._db_path)

    def persist(self, transactions: list[dict]) -> int:
        """Upserts transactions into SQLite using INSERT OR REPLACE."""
        if not transactions:
            return 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO transactions (transaction_id, date, description, amount, currency)
                VALUES (:transaction_id, :date, :description, :amount, :currency);
            """, transactions)
            conn.commit()
        return len(transactions)

    def run(self, state: AgentState) -> dict:
        txs = state.get("transactions", [])
        if not txs:
            return {
                "db_status": "SKIPPED",
                "messages": [HumanMessage(content="StorageAgent: No records received.")],
            }

        count = self.persist(txs)
        return {
            "db_status": "COMMITTED",
            "messages": [
                HumanMessage(content=f"StorageAgent: Stored {count} transactions in {self.db_path}.")
            ],
        }


def storage_agent_node(state: AgentState) -> dict:
    """LangGraph node function for StorageAgent."""
    agent = StorageAgent()
    return agent.run(state)

