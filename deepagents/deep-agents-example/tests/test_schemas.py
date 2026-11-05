import pytest
from pydantic import ValidationError
from src.pipeline.schemas import CleanTransaction, ReconciliationRecord, TransactionBatch


def test_clean_transaction_valid():
    tx = CleanTransaction(
        transaction_id="TX-001",
        date="2026-10-31",
        description="Office Supplies",
        amount=-45.50,
        currency="CHF",
    )
    assert tx.transaction_id == "TX-001"
    assert tx.amount == -45.50
    assert tx.currency == "CHF"


def test_transaction_batch():
    batch = TransactionBatch(
        items=[
            CleanTransaction(
                transaction_id="TX-001",
                date="2026-10-31",
                description="Office Supplies",
                amount=-45.50,
            )
        ]
    )
    assert len(batch.items) == 1
    assert batch.items[0].currency == "CHF"


def test_reconciliation_record():
    rec = ReconciliationRecord(
        transaction_id="TX-001",
        expected_id="EXP-001",
        status="EXACT_MATCH",
        variance=0.0,
        notes="Matched perfectly",
    )
    assert rec.status == "EXACT_MATCH"
    assert rec.variance == 0.0

