from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from src.pipeline.db import init_database
from src.pipeline.harness import build_financial_pipeline


def test_build_financial_pipeline_structure():
    pipeline = build_financial_pipeline()
    assert pipeline is not None


def test_full_pipeline_flow(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_pipeline.db")
    init_database(db_file)
    monkeypatch.setenv("DB_PATH", db_file)
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("DISPATCH_CHANNEL", "webhook")

    csv_file = tmp_path / "test_feed.csv"
    csv_file.write_text(
        "28.10.2026;SUNRISE COMMUNICATIONS AG LAUSANNE;-89.90;CH-TX-001\n"
        "01.11.2026;SERVICES INDUSTRIELS DE GENEVE (SIG);-145.20;CH-TX-003\n",
        encoding="utf-8",
    )

    fake_llm_json = """{
        "items": [
            {
                "transaction_id": "CH-TX-001",
                "date": "2026-10-28",
                "description": "SUNRISE COMMUNICATIONS AG LAUSANNE",
                "amount": -89.90,
                "currency": "CHF"
            },
            {
                "transaction_id": "CH-TX-003",
                "date": "2026-11-01",
                "description": "SERVICES INDUSTRIELS DE GENEVE (SIG)",
                "amount": -145.20,
                "currency": "CHF"
            }
        ]
    }"""

    mock_llm_client = MagicMock()
    mock_llm_client.invoke.return_value = AIMessage(content=fake_llm_json)

    mock_webhook = MagicMock()
    mock_webhook.raise_for_status.return_value = None

    with patch("src.pipeline.agents.reader_agent.get_resilient_lm_studio_client", return_value=mock_llm_client):
        with patch("requests.post", return_value=mock_webhook):
            pipeline = build_financial_pipeline()
            output = pipeline.invoke({
                "raw_file_path": str(csv_file),
                "transactions": [],
                "reconciliation_results": [],
                "db_status": "PENDING",
                "report_path": None,
                "dispatch_status": "PENDING",
                "messages": [],
            })

            assert output["db_status"] == "COMMITTED"
            assert len(output["transactions"]) == 2
            assert len(output["reconciliation_results"]) == 2
            assert output["report_path"] is not None
            assert output["dispatch_status"] == "SENT_WEBHOOK"

