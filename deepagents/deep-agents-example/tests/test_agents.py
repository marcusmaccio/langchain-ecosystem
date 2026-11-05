import os
import sqlite3
from unittest.mock import MagicMock, patch
import pandas as pd
from src.pipeline.agents.dispatch import dispatch_agent_node
from src.pipeline.agents.reader import reader_agent_node
from src.pipeline.agents.reconciliation import reconciliation_agent_node
from src.pipeline.agents.reporting import reporting_agent_node
from src.pipeline.agents.storage import storage_agent_node
from src.pipeline.db import init_database


def test_reader_agent_unsupported_format():
    state = {
        "raw_file_path": "test.txt",
        "transactions": [],
        "reconciliation_results": [],
        "db_status": "PENDING",
        "report_path": None,
        "dispatch_status": "PENDING",
        "messages": [],
    }
    result = reader_agent_node(state)
    assert result["transactions"] == []
    assert "Unsupported format" in result["messages"][0].content


def test_storage_agent_node(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_storage.db")
    init_database(db_file)
    monkeypatch.setenv("DB_PATH", db_file)

    txs = [
        {
            "transaction_id": "TX-1",
            "date": "2026-10-31",
            "description": "Test Entry",
            "amount": -50.0,
            "currency": "CHF",
        }
    ]
    state = {
        "raw_file_path": "feed.csv",
        "transactions": txs,
        "reconciliation_results": [],
        "db_status": "PENDING",
        "report_path": None,
        "dispatch_status": "PENDING",
        "messages": [],
    }
    result = storage_agent_node(state)
    assert result["db_status"] == "COMMITTED"

    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT transaction_id, description FROM transactions WHERE transaction_id='TX-1'")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "TX-1"


def test_reconciliation_agent_node(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_recon.db")
    init_database(db_file)
    monkeypatch.setenv("DB_PATH", db_file)

    txs = [
        # Match exact SUNRISE (-89.90)
        {
            "transaction_id": "TX-1",
            "date": "2026-10-30",
            "description": "SUNRISE COMMUNICATIONS AG",
            "amount": -89.90,
            "currency": "CHF",
        },
        # Partial mismatch SIG (expected -150.00, actual -145.20)
        {
            "transaction_id": "TX-2",
            "date": "2026-11-01",
            "description": "SERVICES INDUSTRIELS DE GENEVE (SIG)",
            "amount": -145.20,
            "currency": "CHF",
        },
        # Unmatched
        {
            "transaction_id": "TX-3",
            "date": "2026-11-02",
            "description": "COFFEE BAR",
            "amount": -5.00,
            "currency": "CHF",
        },
    ]

    state = {
        "raw_file_path": "feed.csv",
        "transactions": txs,
        "reconciliation_results": [],
        "db_status": "COMMITTED",
        "report_path": None,
        "dispatch_status": "PENDING",
        "messages": [],
    }

    result = reconciliation_agent_node(state)
    recon = result["reconciliation_results"]
    assert len(recon) == 3

    status_map = {r["transaction_id"]: r["status"] for r in recon}
    assert status_map["TX-1"] == "EXACT_MATCH"
    assert status_map["TX-2"] == "AMOUNT_MISMATCH"
    assert status_map["TX-3"] == "UNMATCHED"


def test_reporting_agent_node(tmp_path, monkeypatch):
    reports_dir = str(tmp_path / "reports")
    monkeypatch.setenv("REPORTS_DIR", reports_dir)

    state = {
        "raw_file_path": "feed.csv",
        "transactions": [
            {
                "transaction_id": "TX-2",
                "date": "2026-11-01",
                "description": "SIG Energy",
                "amount": -145.20,
                "currency": "CHF",
            }
        ],
        "reconciliation_results": [
            {
                "transaction_id": "TX-2",
                "expected_id": "EXP-POW-003",
                "status": "AMOUNT_MISMATCH",
                "variance": 4.80,
                "notes": "Partial match",
            }
        ],
        "db_status": "COMMITTED",
        "report_path": None,
        "dispatch_status": "PENDING",
        "messages": [],
    }

    result = reporting_agent_node(state)
    assert result["report_path"] is not None
    assert os.path.exists(result["report_path"])
    assert result["report_path"].endswith(".xlsx")


def test_dispatch_agent_node_webhook(tmp_path, monkeypatch):
    xlsx_file = tmp_path / "summary.xlsx"
    xlsx_file.write_text("dummy", encoding="utf-8")

    monkeypatch.setenv("DISPATCH_CHANNEL", "webhook")
    monkeypatch.setenv("DISPATCH_COUNT_THRESHOLD", "1")
    monkeypatch.setenv("DISPATCH_VARIANCE_THRESHOLD", "5.00")

    state = {
        "raw_file_path": "feed.csv",
        "transactions": [],
        "reconciliation_results": [
            {
                "transaction_id": "TX-2",
                "expected_id": "EXP-POW-003",
                "status": "AMOUNT_MISMATCH",
                "variance": 10.00,
                "notes": "Variance breach",
            }
        ],
        "db_status": "COMMITTED",
        "report_path": str(xlsx_file),
        "dispatch_status": "PENDING",
        "messages": [],
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = dispatch_agent_node(state)
        assert result["dispatch_status"] == "SENT_WEBHOOK"
        assert mock_post.called


def test_agent_classes_direct_instantiation(tmp_path, monkeypatch):
    from agents.reader_agent import ReaderAgent
    from agents.storage_agent import StorageAgent
    from agents.reconciliation_agent import ReconciliationAgent
    from agents.reporting_agent import ReportingAgent
    from agents.dispatch_agent import DispatchAgent

    db_file = str(tmp_path / "class_test.db")
    init_database(db_file)

    storage = StorageAgent(db_path=db_file)
    count = storage.persist([
        {"transaction_id": "T1", "date": "2026-10-31", "description": "Loyer", "amount": 2150.0, "currency": "CHF"}
    ])
    assert count == 1

    recon = ReconciliationAgent(db_path=db_file)
    invoices = recon.fetch_expected_invoices()
    assert len(invoices) >= 3

    dispatch = DispatchAgent(count_threshold=5, variance_threshold=100.0)
    assert dispatch.count_threshold == 5
    assert dispatch.variance_threshold == 100.0


