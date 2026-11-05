"""Unit tests for the Bank Transaction Agent (BTA) tools, counters, deduplication, JSON output, and HTML modal."""

import json
from pathlib import Path

from lca_single_agent.tools import (
    TransactionItem,
    find_new_pdf_files,
    generate_transactions_webpage,
    list_pdf_files,
    load_existing_bta_state,
    read_bank_statement_pdf,
    reset_accumulated_transactions,
)
from pypdf import PdfWriter


def _create_blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as f:
        writer.write(f)


def test_list_pdf_files(tmp_path: Path) -> None:
    reset_accumulated_transactions()
    pdf_a = tmp_path / "statement_jan.pdf"
    pdf_b = tmp_path / "statement_feb.pdf"
    _create_blank_pdf(pdf_a)
    _create_blank_pdf(pdf_b)

    result = list_pdf_files.invoke({"path": str(tmp_path)})
    assert "Found 2 PDF file(s)" in result
    assert "statement_jan.pdf" in result
    assert "statement_feb.pdf" in result


def test_read_bank_statement_pdf(tmp_path: Path) -> None:
    reset_accumulated_transactions()
    pdf_path = tmp_path / "sample.pdf"
    _create_blank_pdf(pdf_path)

    result = read_bank_statement_pdf.invoke({"file_path": str(pdf_path)})
    assert "=== FILE: sample.pdf" in result
    assert "--- PAGE 1 ---" in result


def test_bta_counters_deduplication_json_and_modal(tmp_path: Path, monkeypatch) -> None:
    reset_accumulated_transactions()
    monkeypatch.setenv("DISABLE_BROWSER_OPEN", "1")

    pdf_oct = tmp_path / "october.pdf"
    pdf_nov = tmp_path / "november.pdf"
    _create_blank_pdf(pdf_oct)
    _create_blank_pdf(pdf_nov)

    # Register files via list_pdf_files
    list_pdf_files.invoke({"path": str(tmp_path)})

    out_file = tmp_path / "transactions.html"
    json_file = tmp_path / "transactions.json"

    # Provide 3 raw transactions where 1 is an exact duplicate
    sample_txs = [
        TransactionItem(
            date="2026-10-28",
            description="SUNRISE COMMUNICATIONS AG",
            amount=-89.90,
            currency="CHF",
            reference="CH-TX-001",
            bank_name="Banque Migros SA",
            bank_account="Compte privé 63.697.491 / CHF (Loyer) — IBAN CH76 0840 1000 0636 9749 1",
            source_file="october.pdf",
        ),
        TransactionItem(
            date="2026-10-28",
            description="SUNRISE COMMUNICATIONS AG",
            amount=-89.90,
            currency="CHF",
            reference="CH-TX-001",
            bank_name="Banque Migros SA",
            bank_account="Compte privé 63.697.491 / CHF (Loyer) — IBAN CH76 0840 1000 0636 9749 1",
            source_file="october.pdf",
        ),
        TransactionItem(
            date="2026-11-02",
            description="SALARY NOVEMBER",
            amount=4500.00,
            currency="CHF",
            reference="CH-TX-002",
            bank_name="Banque Migros SA",
            bank_account="Compte privé 63.697.491 / CHF (Loyer) — IBAN CH76 0840 1000 0636 9749 1",
            source_file="november.pdf",
        ),
    ]

    result = generate_transactions_webpage.invoke(
        {
            "transactions": [tx.model_dump() for tx in sample_txs],
            "output_path": str(out_file),
            "open_browser": False,
        }
    )

    assert out_file.exists()
    assert json_file.exists()
    assert "Files read: 2" in result
    assert "Period: 2026-10-28 to 2026-11-02" in result
    assert "Raw transactions: 3, Unique: 2, Duplicates removed: 1" in result

    # Verify JSON structure and counters
    payload = json.loads(json_file.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["total_files_read"] == 2
    assert summary["start_date"] == "2026-10-28"
    assert summary["end_date"] == "2026-11-02"
    assert summary["raw_transactions_count"] == 3
    assert summary["unique_transactions_count"] == 2
    assert summary["duplicates_removed_count"] == 1
    assert summary["banks_count"] == 1
    assert summary["bank_accounts_count"] == 1
    assert len(payload["account_sets"]) == 1
    assert payload["account_sets"][0]["bank_name"] == "Banque Migros SA"
    assert "CH76 0840 1000 0636 9749 1" in payload["account_sets"][0]["bank_account"]
    assert len(summary["read_files"]) == 2
    assert len(payload["transactions"]) == 2

    # Verify HTML content: counters, column order, and modal dialog
    html_text = out_file.read_text(encoding="utf-8")
    assert "SUNRISE COMMUNICATIONS AG" in html_text
    assert "SALARY NOVEMBER" in html_text
    assert "Banque Migros SA" in html_text
    assert "CH76 0840 1000 0636 9749 1" in html_text
    assert "2026-10-28 &rarr; 2026-11-02" in html_text
    assert "Raw: 3 &bull; Duplicates: 1" in html_text
    assert '<dialog id="filesModal"' in html_text
    assert "october.pdf" in html_text
    assert "november.pdf" in html_text
    assert html_text.index('<th class="col-amount">Amount</th>') < html_text.index("<th>Source PDF</th>")

    # Verify incremental new-file detection (15-minute watcher helper)
    new_pdfs_none, processed_count = find_new_pdf_files(tmp_path, json_file)
    assert new_pdfs_none == []
    assert processed_count == 2

    # Add a new PDF file and verify find_new_pdf_files detects only the new file
    pdf_dec = tmp_path / "december.pdf"
    _create_blank_pdf(pdf_dec)
    new_pdfs_dec, processed_count_after = find_new_pdf_files(tmp_path, json_file)
    assert len(new_pdfs_dec) == 1
    assert new_pdfs_dec[0].name == "december.pdf"
    assert processed_count_after == 2

    # Verify load_existing_bta_state restores the 2 unique transactions
    loaded_count = load_existing_bta_state(tmp_path, json_file)
    assert loaded_count == 2
