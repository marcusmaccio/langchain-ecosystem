"""Unit tests for the LangGraph StateGraph workflow coordinating BTA and Accounting Agent (AA)."""

import json
from pathlib import Path

from lca_langgraph.workflow import build_bta_aa_graph, get_graph_mermaid
from lca_single_agent.tools import (
    TransactionItem,
    generate_transactions_webpage,
    list_pdf_files,
    reset_accumulated_transactions,
)
from lca_two_agents.tools import generate_balance_webpage
from pypdf import PdfWriter


def _create_blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as f:
        writer.write(f)


def test_langgraph_full_and_incremental_workflow(tmp_path: Path, monkeypatch) -> None:
    """Verify the LangGraph StateGraph coordinates discover_files -> bta_node -> aa_node and skips when no new files arrive."""
    reset_accumulated_transactions()
    monkeypatch.setenv("DISABLE_BROWSER_OPEN", "1")

    pdf_jan = tmp_path / "january.pdf"
    _create_blank_pdf(pdf_jan)

    bta_html = tmp_path / "transactions.html"
    bta_json = tmp_path / "transactions.json"
    balance_html = tmp_path / "balance.html"
    balance_json = tmp_path / "balance.json"

    class DummyMsg:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeBTAAgent:
        def invoke(self, payload: dict) -> dict:
            list_pdf_files.invoke({"path": str(tmp_path)})
            tx = TransactionItem(
                date="2026-01-05",
                description="MARCIN GRUZEWSKI",
                amount=1150.00,
                currency="CHF",
                reference="Bail janvier 2026",
                bank_name="Banque Migros SA",
                bank_account="Compte privé 63.697.491 / CHF (Loyer) — IBAN CH76 0840 1000 0636 9749 1",
                source_file="january.pdf",
            )
            generate_transactions_webpage.invoke(
                {
                    "transactions": [tx.model_dump()],
                    "output_path": str(bta_html),
                    "open_browser": False,
                }
            )
            return {"messages": [DummyMsg("BTA completed extraction for january.pdf")]}

    class FakeAAAgent:
        def invoke(self, payload: dict) -> dict:
            generate_balance_webpage.invoke(
                {
                    "bta_json_path": str(bta_json),
                    "output_path": str(balance_html),
                    "open_browser": False,
                }
            )
            return {"messages": [DummyMsg("AA completed Balance recalculation")]}

    monkeypatch.setattr("lca_langgraph.workflow.build_bta_agent", lambda: FakeBTAAgent())
    monkeypatch.setattr("lca_langgraph.workflow.build_accounting_agent", lambda: FakeAAAgent())

    graph = build_bta_aa_graph()

    # 1. Full workflow run: should traverse discover_files -> bta_node -> aa_node
    state_out = graph.invoke(
        {
            "pdf_path": str(tmp_path),
            "bta_html_path": str(bta_html),
            "bta_json_path": str(bta_json),
            "balance_html_path": str(balance_html),
            "balance_json_path": str(balance_json),
            "incremental": False,
            "open_browser": False,
            "workflow_steps": [],
        }
    )
    assert state_out["should_process"] is True
    assert "BTA completed" in state_out["bta_response"]
    assert "AA completed" in state_out["aa_response"]
    assert len(state_out["workflow_steps"]) == 3
    assert bta_json.exists()
    assert balance_json.exists()

    bal_data = json.loads(balance_json.read_text(encoding="utf-8"))
    assert bal_data["summary"]["total_incoming"] == 1150.0
    assert bal_data["summary"]["net_balance"] == 1150.0

    # 2. Incremental workflow run with NO new files: should short-circuit at discover_files -> END
    inc_state = graph.invoke(
        {
            "pdf_path": str(tmp_path),
            "bta_html_path": str(bta_html),
            "bta_json_path": str(bta_json),
            "balance_html_path": str(balance_html),
            "balance_json_path": str(balance_json),
            "incremental": True,
            "open_browser": False,
            "workflow_steps": [],
        }
    )
    assert inc_state["should_process"] is False
    assert inc_state["new_files"] == []
    assert len(inc_state["workflow_steps"]) == 1
    assert "No new PDF files" in inc_state["workflow_steps"][0]


def test_graph_mermaid_export() -> None:
    mermaid = get_graph_mermaid()
    assert "discover_files" in mermaid
    assert "bta_node" in mermaid
    assert "aa_node" in mermaid
