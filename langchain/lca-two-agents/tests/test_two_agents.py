"""Unit tests for the two-agent system reusing BTA from lca-single-agent + Accounting Agent (AA)."""

import json
from pathlib import Path

from lca_single_agent.tools import (
    TransactionItem,
    generate_transactions_webpage,
    list_pdf_files,
    reset_accumulated_transactions,
)
from lca_two_agents.accounting_agent import notify_accounting_agent
from lca_two_agents.tools import (
    generate_balance_webpage,
    read_bta_transactions_json,
)
from pypdf import PdfWriter


def _create_blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as f:
        writer.write(f)


def test_bta_to_accounting_agent_balance_flow(tmp_path: Path, monkeypatch) -> None:
    reset_accumulated_transactions()
    monkeypatch.setenv("DISABLE_BROWSER_OPEN", "1")

    pdf_jan = tmp_path / "january.pdf"
    pdf_feb = tmp_path / "february.pdf"
    _create_blank_pdf(pdf_jan)
    _create_blank_pdf(pdf_feb)

    list_pdf_files.invoke({"path": str(tmp_path)})

    bta_html = tmp_path / "transactions.html"
    bta_json = tmp_path / "transactions.json"
    balance_html = tmp_path / "balance.html"
    balance_json = tmp_path / "balance.json"

    sample_txs = [
        TransactionItem(
            date="2026-01-05",
            description="MARCIN GRUZEWSKI",
            amount=1150.00,
            currency="CHF",
            reference="Bail janvier 2026",
            bank_name="Banque Migros SA",
            bank_account="Compte privé 63.697.491 / CHF (Loyer) — IBAN CH76 0840 1000 0636 9749 1",
            source_file="january.pdf",
        ),
        TransactionItem(
            date="2026-02-06",
            description="Sunrise LLC",
            amount=-259.20,
            currency="CHF",
            reference="Invoice 001",
            bank_name="Banque Migros SA",
            bank_account="Compte privé 63.697.491 / CHF (Loyer) — IBAN CH76 0840 1000 0636 9749 1",
            source_file="february.pdf",
        ),
    ]

    # Step 1: BTA (imported from lca-single-agent) generates transactions.json and transactions.html
    bta_res = generate_transactions_webpage.invoke(
        {
            "transactions": [tx.model_dump() for tx in sample_txs],
            "output_path": str(bta_html),
            "open_browser": False,
        }
    )
    assert bta_json.exists()
    assert "Files read: 2" in bta_res

    # Step 2: Accounting Agent reads BTA JSON
    read_res = read_bta_transactions_json.invoke({"json_path": str(bta_json)})
    assert "INCOMING" in read_res
    assert "EXPENSE" in read_res
    assert "MARCIN GRUZEWSKI" in read_res

    # Step 3: Accounting Agent generates Balance webpage (balance.html & balance.json)
    aa_res = generate_balance_webpage.invoke(
        {
            "bta_json_path": str(bta_json),
            "output_path": str(balance_html),
            "open_browser": False,
        }
    )
    assert balance_html.exists()
    assert balance_json.exists()
    assert "Incoming: +1,150.00 CHF" in aa_res
    assert "Expenses: -259.20 CHF" in aa_res
    assert "Net Balance: +890.80 CHF" in aa_res

    # Verify Balance HTML table columns: Date, Description, Incoming, Expenses, Source PDF
    html_text = balance_html.read_text(encoding="utf-8")
    idx_date = html_text.index("<th>Date</th>")
    idx_desc = html_text.index("<th>Description</th>")
    idx_inc = html_text.index('<th class="col-amount">Incoming</th>')
    idx_exp = html_text.index('<th class="col-amount">Expenses</th>')
    idx_src = html_text.index("<th>Source PDF</th>")
    assert idx_date < idx_desc < idx_inc < idx_exp < idx_src

    # Verify Balance JSON totals and account_balances per Bank and Bank Account
    bal_payload = json.loads(balance_json.read_text(encoding="utf-8"))
    assert bal_payload["summary"]["total_incoming"] == 1150.0
    assert bal_payload["summary"]["total_expenses"] == 259.2
    assert bal_payload["summary"]["net_balance"] == 890.8
    assert bal_payload["summary"]["banks_count"] == 1
    assert bal_payload["summary"]["bank_accounts_count"] == 1
    assert len(bal_payload["account_balances"]) == 1
    assert bal_payload["account_balances"][0]["bank_name"] == "Banque Migros SA"
    assert "CH76 0840 1000 0636 9749 1" in bal_payload["account_balances"][0]["bank_account"]
    assert len(bal_payload["entries"]) == 2


def test_bta_notify_accounting_agent_handoff(tmp_path: Path, monkeypatch) -> None:
    """Verify BTA can communicate with AA via notify_accounting_agent to trigger Balance recalculation."""
    bta_json = tmp_path / "transactions.json"
    balance_html = tmp_path / "balance.html"

    class DummyMsg:
        content = "Balance recalculated: +1,150.00 CHF incoming, -259.20 CHF expenses."

    class DummyAA:
        def __init__(self) -> None:
            self.invoked_prompts: list[str] = []

        def invoke(self, payload: dict) -> dict:
            self.invoked_prompts.append(payload["messages"][0]["content"])
            return {"messages": [DummyMsg()]}

    dummy_aa = DummyAA()
    monkeypatch.setattr("lca_two_agents.accounting_agent.build_accounting_agent", lambda: dummy_aa)

    res = notify_accounting_agent.invoke(
        {
            "bta_json_path": str(bta_json),
            "balance_output_path": str(balance_html),
            "reason": "New PDF statement 20260831 parsed by BTA",
        }
    )
    assert "Accounting Agent (AA) notified and completed Balance recalculation" in res
    assert len(dummy_aa.invoked_prompts) == 1
    assert "New PDF statement 20260831 parsed by BTA" in dummy_aa.invoked_prompts[0]

