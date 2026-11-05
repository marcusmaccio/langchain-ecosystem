"""Tools and state tracking for the Bank Transaction Agent (BTA)."""

import html
import json
import os
import re
import webbrowser
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from pypdf import PdfReader


class TransactionItem(BaseModel):
    """Schema for a single bank transaction row."""

    date: str = Field(description="Transaction date in YYYY-MM-DD format")
    description: str = Field(description="Merchant, payee, or transaction description")
    amount: float = Field(
        description="Transaction amount as a number (negative for debit/expense, positive for credit/income)"
    )
    currency: str = Field(default="CHF", description="Currency code (e.g., CHF, EUR, USD)")
    reference: str = Field(default="", description="Optional booking reference or category")
    bank_name: str = Field(
        default="",
        description="Name of the bank identified from the PDF statement (e.g., 'Banque Migros SA')",
    )
    bank_account: str = Field(
        default="",
        description="Bank account identifier / IBAN / account type from the PDF statement (e.g., 'Compte privé 63.697.491 / CHF (Loyer) — IBAN CH76 0840 1000 0636 9749 1')",
    )
    source_file: str = Field(default="", description="Name or path of the source PDF file")


class ReadFileRecord(BaseModel):
    """Metadata for a single PDF file tracked by the Bank Transaction Agent."""

    file_name: str
    file_path: str
    file_uri: str
    bank_name: str = ""
    bank_account: str = ""


class BankAccountTransactionSet(BaseModel):
    """A set of transactions grouped by (Bank, Bank Account) in the BTA output."""

    bank_name: str
    bank_account: str
    currency: str = "CHF"
    start_date: str = "—"
    end_date: str = "—"
    transactions_count: int = 0
    total_credits: float = 0.0
    total_debits: float = 0.0
    net_cashflow: float = 0.0
    transactions: list[TransactionItem] = Field(default_factory=list)


class BankTransactionSummary(BaseModel):
    """Counters and metadata tracked by the Bank Transaction Agent (BTA)."""

    agent_name: str = "Bank Transaction Agent (BTA)"
    source_directory: str = ""
    total_files_read: int = 0
    read_files: list[ReadFileRecord] = Field(default_factory=list)
    banks_count: int = 0
    bank_accounts_count: int = 0
    start_date: str = "—"
    end_date: str = "—"
    raw_transactions_count: int = 0
    unique_transactions_count: int = 0
    duplicates_removed_count: int = 0
    total_credits: float = 0.0
    total_debits: float = 0.0
    net_cashflow: float = 0.0
    currency: str = "CHF"
    generated_at: str = ""


class BankTransactionReport(BaseModel):
    """Complete JSON payload persisted to reports/transactions.json."""

    summary: BankTransactionSummary
    account_sets: list[BankAccountTransactionSet] = Field(default_factory=list)
    transactions: list[TransactionItem] = Field(default_factory=list)


# Session state tracked by BTA
_DISCOVERED_PDF_PATHS: dict[str, Path] = {}
_PDF_BANK_METADATA: dict[str, tuple[str, str]] = {}
_RAW_TRANSACTIONS: list[TransactionItem] = []
_SOURCE_DIRECTORY: str = ""


def reset_accumulated_transactions() -> None:
    """Clear BTA session counters and tracked state before a new run."""
    global _SOURCE_DIRECTORY
    _DISCOVERED_PDF_PATHS.clear()
    _PDF_BANK_METADATA.clear()
    _RAW_TRANSACTIONS.clear()
    _SOURCE_DIRECTORY = ""


def _scan_directory_pdfs(path: str | Path) -> list[Path]:
    """Return sorted, deduplicated PDF Path objects from a directory or single file path."""
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return []
    if target.is_file():
        return [target] if target.suffix.lower() == ".pdf" else []

    pdf_files = sorted(target.glob("*.pdf")) + sorted(target.glob("*.PDF"))
    seen: set[Path] = set()
    unique_pdfs: list[Path] = []
    for p in pdf_files:
        resolved = p.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_pdfs.append(resolved)
    return unique_pdfs


def find_new_pdf_files(
    path: str | Path,
    json_cache_path: str | Path = "reports/transactions.json",
) -> tuple[list[Path], int]:
    """Compare PDFs on disk against already-read files in transactions.json.

    Returns:
        Tuple of (new_pdf_paths, already_processed_count).
    """
    all_pdfs = _scan_directory_pdfs(path)
    cache_file = Path(json_cache_path).expanduser().resolve()
    if not cache_file.exists():
        return all_pdfs, 0

    try:
        raw_data = json.loads(cache_file.read_text(encoding="utf-8"))
        summary_data = raw_data.get("summary", {}) if isinstance(raw_data, dict) else {}
        known_names = {
            rf.get("file_name", "")
            for rf in summary_data.get("read_files", [])
            if rf.get("file_name")
        }
        if not known_names and isinstance(raw_data, dict):
            known_names = {
                Path(tx.get("source_file", "")).name
                for tx in raw_data.get("transactions", [])
                if tx.get("source_file")
            }
    except Exception:
        return all_pdfs, 0

    new_pdfs = [p for p in all_pdfs if p.name not in known_names]
    return new_pdfs, len(known_names)


def load_existing_bta_state(
    directory_path: str | Path,
    json_cache_path: str | Path = "reports/transactions.json",
) -> int:
    """Pre-load existing transactions and registered PDF files from transactions.json into BTA memory."""
    global _SOURCE_DIRECTORY
    reset_accumulated_transactions()

    target = Path(directory_path).expanduser().resolve()
    _SOURCE_DIRECTORY = str(target if target.is_dir() else target.parent)

    for pdf in _scan_directory_pdfs(target):
        _register_pdf_path(pdf)

    cache_file = Path(json_cache_path).expanduser().resolve()
    if not cache_file.exists():
        return 0

    raw_data = json.loads(cache_file.read_text(encoding="utf-8"))
    raw_items = raw_data.get("transactions", []) if isinstance(raw_data, dict) else raw_data
    for item in raw_items:
        _RAW_TRANSACTIONS.append(TransactionItem(**item))
    return len(_RAW_TRANSACTIONS)


def normalize_date_str(date_str: str) -> str:
    """Normalize DD.MM.YY or DD.MM.YYYY into YYYY-MM-DD for accurate chronological sorting."""
    cleaned = date_str.strip()
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{2,4})$", cleaned)
    if m:
        day, month, year = m.groups()
        if len(year) == 2:
            year = f"20{year}"
        return f"{year}-{month}-{day}"
    return cleaned


def extract_bank_metadata_from_text(text: str) -> tuple[str, str]:
    """Extract (bank_name, bank_account) from raw statement page text."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bank_name = ""
    if lines:
        # First non-empty line on Swiss bank statements is typically the bank name (e.g. "Banque Migros SA")
        first_line = lines[0]
        if any(w in first_line.lower() for w in ("banque", "bank", "migros", "ubs", "raiffeisen", "postfinance", "bcv", "credit", "zkb")):
            bank_name = first_line
        else:
            for line in lines[:10]:
                if any(w in line.lower() for w in ("banque", "bank", "migros", "ubs", "raiffeisen", "postfinance", "bcv")):
                    bank_name = line
                    break

    iban_match = re.search(r"IBAN\s+([A-Z]{2}\d{2}(?:\s+[A-Z0-9]{4}){3,6}(?:\s+[A-Z0-9]{1,4})?)", text)
    iban = iban_match.group(1).strip() if iban_match else ""

    acct_type = ""
    acct_label = ""
    for idx, line in enumerate(lines[:20]):
        if re.search(r"^(Compte\s+|Account\s+|Konto\s+|Portefeuille\s+)", line, re.IGNORECASE) and not line.lower().startswith("portefeuille"):
            acct_type = line
            if idx + 1 < len(lines) and not lines[idx + 1].upper().startswith("IBAN"):
                next_line = lines[idx + 1]
                if len(next_line) < 35 and not any(ch.isdigit() for ch in next_line):
                    acct_label = next_line
            break

    parts: list[str] = []
    if acct_type:
        if acct_label:
            parts.append(f"{acct_type} ({acct_label})")
        else:
            parts.append(acct_type)
    if iban:
        parts.append(f"IBAN {iban}")

    bank_account = " — ".join(parts)
    return bank_name, bank_account


def _inspect_pdf_bank_metadata(pdf_path: Path) -> tuple[str, str]:
    """Read page 1 of a PDF file to extract and cache (bank_name, bank_account)."""
    name = pdf_path.name
    if name in _PDF_BANK_METADATA:
        return _PDF_BANK_METADATA[name]
    try:
        reader = PdfReader(str(pdf_path))
        if reader.pages:
            first_page_text = (reader.pages[0].extract_text() or "").strip()
            bank_name, bank_account = extract_bank_metadata_from_text(first_page_text)
            if bank_name or bank_account:
                _PDF_BANK_METADATA[name] = (
                    bank_name or "Unknown Bank",
                    bank_account or "Unknown Account",
                )
                return _PDF_BANK_METADATA[name]
    except Exception:
        pass
    return ("", "")


def _register_pdf_path(pdf_path: Path) -> None:
    """Record discovered PDF full path by filename and inspect its bank/account metadata."""
    global _SOURCE_DIRECTORY
    resolved = pdf_path.expanduser().resolve()
    _DISCOVERED_PDF_PATHS[resolved.name] = resolved
    if not _SOURCE_DIRECTORY:
        _SOURCE_DIRECTORY = str(resolved.parent)
    _inspect_pdf_bank_metadata(resolved)


def resolve_pdf_path(source_file: str) -> Path | None:
    """Resolve a source PDF filename or path to its full Path on disk if available."""
    if not source_file:
        return None

    basename = Path(source_file).name
    if basename in _DISCOVERED_PDF_PATHS:
        return _DISCOVERED_PDF_PATHS[basename]

    candidate = Path(source_file).expanduser()
    if candidate.is_absolute() and candidate.exists():
        resolved = candidate.resolve()
        _register_pdf_path(resolved)
        return resolved

    env_dir = os.getenv("BANK_PDF_SOURCE_DIR") or _SOURCE_DIRECTORY
    if env_dir:
        env_candidate = Path(env_dir).expanduser().resolve() / basename
        if env_candidate.exists():
            resolved = env_candidate.resolve()
            _register_pdf_path(resolved)
            return resolved

    if candidate.exists():
        resolved = candidate.resolve()
        _register_pdf_path(resolved)
        return resolved
    return None


def _enrich_transaction_bank_info(item: TransactionItem) -> TransactionItem:
    """Ensure bank_name and bank_account are populated on a TransactionItem using PDF metadata if needed."""
    basename = Path(item.source_file).name if item.source_file else ""
    pdf_bank, pdf_acct = _PDF_BANK_METADATA.get(basename, ("", ""))

    # Prefer canonical PDF-extracted metadata when available so all files from the same account group cleanly
    bank_name = pdf_bank or item.bank_name.strip() or "Unknown Bank"
    bank_account = pdf_acct or item.bank_account.strip() or "Default Account"
    return item.model_copy(
        update={
            "date": normalize_date_str(item.date),
            "bank_name": bank_name,
            "bank_account": bank_account,
        }
    )


def _deduplicate_transactions(raw_items: list[TransactionItem]) -> list[TransactionItem]:
    """Deduplicate transactions while normalizing dates, enriching bank info, and preserving chronological order."""
    seen: set[tuple[str, str, str, float, str, str, str]] = set()
    unique: list[TransactionItem] = []
    for item in raw_items:
        enriched = _enrich_transaction_bank_info(item)
        key = (
            enriched.date,
            enriched.description.strip(),
            enriched.reference.strip(),
            round(enriched.amount, 2),
            enriched.bank_name,
            enriched.bank_account,
            Path(enriched.source_file).name,
        )
        if key not in seen:
            seen.add(key)
            unique.append(enriched)
    unique.sort(key=lambda x: (x.bank_name, x.bank_account, x.date, Path(x.source_file).name))
    return unique


def build_bta_report(raw_items: list[TransactionItem]) -> BankTransactionReport:
    """Compute BTA counters, group transactions by (Bank, Bank Account), and build BankTransactionReport."""
    for tx in raw_items:
        resolve_pdf_path(tx.source_file)

    unique_txs = _deduplicate_transactions(raw_items)
    raw_count = len(raw_items)
    unique_count = len(unique_txs)
    duplicates_count = raw_count - unique_count

    dates = sorted(tx.date for tx in unique_txs if tx.date)
    start_date = dates[0] if dates else "—"
    end_date = dates[-1] if dates else "—"

    # Group transactions into sets by (bank_name, bank_account)
    grouped: dict[tuple[str, str], list[TransactionItem]] = {}
    for tx in unique_txs:
        group_key = (tx.bank_name, tx.bank_account)
        grouped.setdefault(group_key, []).append(tx)

    account_sets: list[BankAccountTransactionSet] = []
    for (b_name, b_acct), group_txs in sorted(grouped.items(), key=lambda item: item[0]):
        group_txs.sort(key=lambda x: (x.date, Path(x.source_file).name))
        g_dates = sorted(t.date for t in group_txs if t.date)
        g_credits = round(sum(t.amount for t in group_txs if t.amount > 0), 2)
        g_debits = round(sum(t.amount for t in group_txs if t.amount < 0), 2)
        g_net = round(sum(t.amount for t in group_txs), 2)
        g_curr = group_txs[0].currency if group_txs else "CHF"
        account_sets.append(
            BankAccountTransactionSet(
                bank_name=b_name,
                bank_account=b_acct,
                currency=g_curr,
                start_date=g_dates[0] if g_dates else "—",
                end_date=g_dates[-1] if g_dates else "—",
                transactions_count=len(group_txs),
                total_credits=g_credits,
                total_debits=g_debits,
                net_cashflow=g_net,
                transactions=group_txs,
            )
        )

    # Collect ordered list of read PDF files with their identified bank & account
    sorted_paths = sorted(_DISCOVERED_PDF_PATHS.values(), key=lambda p: p.name)
    read_files = [
        ReadFileRecord(
            file_name=p.name,
            file_path=str(p),
            file_uri=p.as_uri(),
            bank_name=_PDF_BANK_METADATA.get(p.name, ("", ""))[0],
            bank_account=_PDF_BANK_METADATA.get(p.name, ("", ""))[1],
        )
        for p in sorted_paths
    ]
    if not read_files:
        unique_names = sorted({Path(tx.source_file).name for tx in unique_txs if tx.source_file})
        read_files = [
            ReadFileRecord(file_name=name, file_path=name, file_uri="")
            for name in unique_names
        ]

    unique_banks = {s.bank_name for s in account_sets if s.bank_name}
    total_credits = round(sum(t.amount for t in unique_txs if t.amount > 0), 2)
    total_debits = round(sum(t.amount for t in unique_txs if t.amount < 0), 2)
    net_cashflow = round(sum(t.amount for t in unique_txs), 2)
    default_currency = unique_txs[0].currency if unique_txs else "CHF"
    source_dir = os.getenv("BANK_PDF_SOURCE_DIR") or _SOURCE_DIRECTORY

    summary = BankTransactionSummary(
        source_directory=source_dir,
        total_files_read=len(read_files),
        read_files=read_files,
        banks_count=len(unique_banks),
        bank_accounts_count=len(account_sets),
        start_date=start_date,
        end_date=end_date,
        raw_transactions_count=raw_count,
        unique_transactions_count=unique_count,
        duplicates_removed_count=duplicates_count,
        total_credits=total_credits,
        total_debits=total_debits,
        net_cashflow=net_cashflow,
        currency=default_currency,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    return BankTransactionReport(
        summary=summary,
        account_sets=account_sets,
        transactions=unique_txs,
    )


@tool
def list_pdf_files(path: str) -> str:
    """List all PDF files in a given directory path, count them, and identify their Bank and Bank Account.

    Args:
        path: Absolute or relative path to a folder containing bank statement PDFs, or a single PDF file.
    """
    global _SOURCE_DIRECTORY
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return f"Error: Path '{target}' does not exist."

    if target.is_file():
        if target.suffix.lower() == ".pdf":
            _SOURCE_DIRECTORY = str(target.parent)
            _register_pdf_path(target)
            b_name, b_acct = _PDF_BANK_METADATA.get(target.name, ("", ""))
            return f"Found 1 PDF file:\n- {target} [Bank: {b_name} | Account: {b_acct}]"
        return f"Error: File '{target}' is not a PDF file."

    _SOURCE_DIRECTORY = str(target)
    pdf_files = sorted(target.glob("*.pdf")) + sorted(target.glob("*.PDF"))
    seen: set[Path] = set()
    unique_pdfs: list[Path] = []
    for p in pdf_files:
        resolved = p.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_pdfs.append(resolved)
            _register_pdf_path(resolved)

    if not unique_pdfs:
        return f"No PDF files found in directory '{target}'."

    lines = [f"Found {len(unique_pdfs)} PDF file(s) in '{target}':"]
    for pdf in unique_pdfs:
        b_name, b_acct = _PDF_BANK_METADATA.get(pdf.name, ("", ""))
        lines.append(f"- {pdf} [Bank: {b_name} | Account: {b_acct}]")
    return "\n".join(lines)


def _compact_statement_text(text: str) -> str:
    """Remove repetitive bank footer disclaimers to keep LLM context compact."""
    cutoff_markers = [
        "Nous vous prions de vérifier cet extrait",
        "Avec nos meilleures salutations",
    ]
    cleaned = text
    for marker in cutoff_markers:
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[0].strip()
    return cleaned


@tool
def read_bank_statement_pdf(file_path: str) -> str:
    """Extract text and Bank/Account metadata from a bank statement PDF file or all PDFs in a directory.

    Args:
        file_path: Absolute or relative path to a PDF file or a directory containing PDF files.
    """
    global _SOURCE_DIRECTORY
    target = Path(file_path).expanduser().resolve()
    if not target.exists():
        return f"Error: Path '{target}' not found."

    if target.is_dir():
        _SOURCE_DIRECTORY = str(target)
        pdf_files = sorted(target.glob("*.pdf")) + sorted(target.glob("*.PDF"))
        seen: set[Path] = set()
        unique_pdfs: list[Path] = []
        for p in pdf_files:
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                unique_pdfs.append(resolved)
        if not unique_pdfs:
            return f"No PDF files found in directory '{target}'."
    else:
        if target.suffix.lower() != ".pdf":
            return f"Error: File '{target}' is not a PDF."
        _SOURCE_DIRECTORY = str(target.parent)
        unique_pdfs = [target]

    all_docs: list[str] = []
    for pdf in unique_pdfs:
        _register_pdf_path(pdf)
        b_name, b_acct = _PDF_BANK_METADATA.get(pdf.name, ("", ""))
        try:
            reader = PdfReader(str(pdf))
            extracted_pages: list[str] = [
                f"=== FILE: {pdf.name} | BANK: {b_name} | ACCOUNT: {b_acct} ==="
            ]
            for idx, page in enumerate(reader.pages, start=1):
                text = _compact_statement_text((page.extract_text() or "").strip())
                if text:
                    extracted_pages.append(f"--- PAGE {idx} ---\n{text}")
                else:
                    extracted_pages.append(f"--- PAGE {idx} ---\n[No extractable text on page {idx}]")
            all_docs.append("\n".join(extracted_pages))
        except Exception as exc:
            all_docs.append(f"Error reading PDF '{pdf.name}': {exc}")

    return "\n\n".join(all_docs)


def _format_source_pdf_cell(source_file: str) -> str:
    """Format a Source PDF cell with a clickable file:// link when resolvable."""
    resolved_pdf = resolve_pdf_path(source_file)
    display_source = Path(source_file).name if source_file else "—"
    if resolved_pdf is not None:
        pdf_uri = resolved_pdf.as_uri()
        return (
            f'<a href="{html.escape(pdf_uri)}" target="_blank" rel="noopener" '
            f'class="badge badge-link" title="{html.escape(str(resolved_pdf))}">'
            f"{html.escape(display_source)}</a>"
        )
    if source_file and source_file.startswith("/"):
        pdf_uri = Path(source_file).as_uri()
        return (
            f'<a href="{html.escape(pdf_uri)}" target="_blank" rel="noopener" '
            f'class="badge badge-link" title="{html.escape(source_file)}">'
            f"{html.escape(display_source)}</a>"
        )
    return f'<span class="badge">{html.escape(display_source)}</span>'


def build_transactions_html(
    report: BankTransactionReport,
    title: str = "Bank Transaction Agent (BTA) — Statement Report",
) -> str:
    """Generate a standalone HTML webpage displaying BTA counters, read files modal, and transaction sets per Bank & Bank Account."""
    summary = report.summary

    # Build modal rows for read files
    modal_file_rows: list[str] = []
    for f_idx, rf in enumerate(summary.read_files, start=1):
        open_link = (
            f'<a href="{html.escape(rf.file_uri)}" target="_blank" rel="noopener" class="badge badge-link">'
            f"Open PDF &nearr;</a>"
            if rf.file_uri
            else '<span class="badge">—</span>'
        )
        modal_file_rows.append(
            f"""
            <tr>
                <td class="col-index">{f_idx}</td>
                <td class="file-name">{html.escape(rf.file_name)}</td>
                <td>{html.escape(rf.bank_name or "—")}</td>
                <td>{html.escape(rf.bank_account or "—")}</td>
                <td class="file-path"><code>{html.escape(rf.file_path)}</code></td>
                <td style="text-align: right; white-space: nowrap;">{open_link}</td>
            </tr>"""
        )
    modal_files_block = "\n".join(modal_file_rows) if modal_file_rows else (
        '<tr><td colspan="6" class="empty-row">No files recorded.</td></tr>'
    )

    # Render each Bank & Bank Account transaction set section
    account_sections_html: list[str] = []
    for set_idx, acct_set in enumerate(report.account_sets, start=1):
        rows_html: list[str] = []
        for idx, tx in enumerate(acct_set.transactions, start=1):
            amt_class = "amount-positive" if tx.amount >= 0 else "amount-negative"
            amt_prefix = "+" if tx.amount > 0 else ""
            source_cell = _format_source_pdf_cell(tx.source_file)

            rows_html.append(
                f"""
                <tr class="tx-row">
                    <td class="col-index">{idx}</td>
                    <td class="col-date">{html.escape(tx.date)}</td>
                    <td class="col-desc">{html.escape(tx.description)}</td>
                    <td class="col-ref">{html.escape(tx.reference or "—")}</td>
                    <td class="col-amount {amt_class}">{amt_prefix}{tx.amount:,.2f} {html.escape(tx.currency)}</td>
                    <td class="col-source">{source_cell}</td>
                </tr>"""
            )

        rows_block = "\n".join(rows_html) if rows_html else (
            '<tr><td colspan="6" class="empty-row">No transactions in this account set.</td></tr>'
        )
        net_cls = "amount-positive" if acct_set.net_cashflow >= 0 else "amount-negative"
        net_pre = "+" if acct_set.net_cashflow > 0 else ""

        account_sections_html.append(
            f"""
            <details class="account-section">
                <summary class="account-banner">
                    <div class="account-banner-left">
                        <span class="bank-pill">&#127974; {html.escape(acct_set.bank_name)}</span>
                        <h2 class="account-title">{html.escape(acct_set.bank_account)}</h2>
                        <div class="account-period">
                            Period: <strong>{html.escape(acct_set.start_date)} &rarr; {html.escape(acct_set.end_date)}</strong>
                            &bull; {acct_set.transactions_count} transaction(s)
                        </div>
                    </div>
                    <div class="account-banner-right">
                        <div class="account-banner-stats">
                            <div class="mini-stat">
                                <span class="mini-label">Credits</span>
                                <span class="mini-val amount-positive">+{acct_set.total_credits:,.2f} {html.escape(acct_set.currency)}</span>
                            </div>
                            <div class="mini-stat">
                                <span class="mini-label">Debits</span>
                                <span class="mini-val amount-negative">{acct_set.total_debits:,.2f} {html.escape(acct_set.currency)}</span>
                            </div>
                            <div class="mini-stat">
                                <span class="mini-label">Net Cashflow</span>
                                <span class="mini-val {net_cls}">{net_pre}{acct_set.net_cashflow:,.2f} {html.escape(acct_set.currency)}</span>
                            </div>
                        </div>
                        <span class="expand-toggle">
                            <span class="label-closed">Show Details &#9662;</span>
                            <span class="label-open">Hide Details &#9652;</span>
                        </span>
                    </div>
                </summary>

                <div class="table-wrapper">
                    <table class="txTable">
                        <thead>
                            <tr>
                                <th class="col-index">#</th>
                                <th>Date</th>
                                <th>Description</th>
                                <th>Reference</th>
                                <th class="col-amount">Amount</th>
                                <th>Source PDF</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_block}
                        </tbody>
                    </table>
                </div>
            </details>"""
        )

    sections_block = "\n".join(account_sections_html) if account_sections_html else (
        '<div class="table-wrapper"><p class="empty-row">No transaction sets found.</p></div>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{html.escape(title)}</title>
    <style>
        :root {{
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --accent: #2563eb;
            --positive: #16a34a;
            --negative: #dc2626;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            padding: 32px 20px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text-main);
        }}
        .container {{
            max-width: 1240px;
            margin: 0 auto;
        }}
        header {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            gap: 12px;
        }}
        .header-left h1 {{
            margin: 0 0 4px 0;
            font-size: 1.75rem;
            font-weight: 700;
        }}
        .meta {{
            color: var(--text-muted);
            font-size: 0.9rem;
        }}
        .nav-pills {{
            display: flex;
            gap: 8px;
        }}
        .nav-pill {{
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 0.88rem;
            font-weight: 600;
            text-decoration: none;
            border: 1px solid var(--border);
            background: var(--card-bg);
            color: var(--text-main);
        }}
        .nav-pill.active {{
            background: var(--accent);
            color: #ffffff;
            border-color: var(--accent);
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(185px, 1fr));
            gap: 14px;
            margin-bottom: 24px;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px 18px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .card-label {{
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 6px;
            font-weight: 600;
        }}
        .card-value {{
            font-size: 1.3rem;
            font-weight: 700;
            font-variant-numeric: tabular-nums;
        }}
        .card-sub {{
            margin-top: 6px;
            font-size: 0.8rem;
            color: var(--text-muted);
        }}
        .modal-trigger-link {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            color: var(--accent);
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            background: none;
            border: none;
            padding: 0;
            font-size: 0.82rem;
        }}
        .modal-trigger-link:hover {{
            text-decoration: underline;
        }}
        .toolbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .search-input {{
            width: 100%;
            max-width: 380px;
            padding: 10px 14px;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 0.95rem;
            background: var(--card-bg);
        }}
        .account-section {{
            margin-bottom: 24px;
        }}
        .account-banner {{
            background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
            border: 1px solid #bfdbfe;
            border-radius: 12px;
            padding: 18px 22px;
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            cursor: pointer;
            list-style: none;
            user-select: none;
            transition: background 0.15s ease, border-radius 0.15s ease;
        }}
        .account-banner::-webkit-details-marker {{
            display: none;
        }}
        .account-banner:hover {{
            background: linear-gradient(135deg, #dbeafe 0%, #f1f5f9 100%);
        }}
        details.account-section[open] > .account-banner {{
            border-radius: 12px 12px 0 0;
        }}
        .account-banner-right {{
            display: flex;
            align-items: center;
            gap: 20px;
            flex-wrap: wrap;
        }}
        .expand-toggle {{
            display: inline-flex;
            align-items: center;
            padding: 6px 12px;
            border-radius: 8px;
            background: #ffffff;
            border: 1px solid #bfdbfe;
            color: #1d4ed8;
            font-size: 0.82rem;
            font-weight: 600;
            white-space: nowrap;
        }}
        details.account-section:not([open]) .label-open {{
            display: none;
        }}
        details.account-section[open] .label-closed {{
            display: none;
        }}
        .bank-pill {{
            display: inline-block;
            background: #1d4ed8;
            color: #ffffff;
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            padding: 3px 10px;
            border-radius: 999px;
            margin-bottom: 6px;
        }}
        .account-title {{
            margin: 2px 0 4px 0;
            font-size: 1.15rem;
            font-weight: 700;
            color: #0f172a;
        }}
        .account-period {{
            font-size: 0.85rem;
            color: var(--text-muted);
        }}
        .account-banner-stats {{
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }}
        .mini-stat {{
            display: flex;
            flex-direction: column;
            align-items: flex-end;
        }}
        .mini-label {{
            font-size: 0.72rem;
            text-transform: uppercase;
            color: var(--text-muted);
            font-weight: 600;
        }}
        .mini-val {{
            font-size: 1.05rem;
            font-weight: 700;
            font-variant-numeric: tabular-nums;
        }}
        .table-wrapper {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-top: none;
            border-radius: 0 0 12px 12px;
            overflow-x: auto;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.94rem;
        }}
        th, td {{
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background: #f1f5f9;
            font-weight: 600;
            color: #334155;
            white-space: nowrap;
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        tr:hover td {{
            background: #f8fafc;
        }}
        .col-index {{ color: var(--text-muted); width: 48px; }}
        .col-date {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
        .col-amount {{
            text-align: right;
            white-space: nowrap;
            font-weight: 600;
            font-variant-numeric: tabular-nums;
        }}
        th.col-amount {{ text-align: right; }}
        .amount-positive {{ color: var(--positive); }}
        .amount-negative {{ color: var(--negative); }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            font-size: 0.78rem;
            border-radius: 6px;
            background: #e2e8f0;
            color: #334155;
            text-decoration: none;
            transition: background 0.15s ease, color 0.15s ease;
        }}
        a.badge-link {{
            background: #dbeafe;
            color: #1d4ed8;
            font-weight: 500;
        }}
        a.badge-link:hover {{
            background: #bfdbfe;
            color: #1e40af;
            text-decoration: underline;
        }}
        .empty-row {{
            text-align: center;
            color: var(--text-muted);
            padding: 32px;
        }}
        dialog.files-modal {{
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 0;
            width: min(1040px, 95vw);
            max-height: 85vh;
            box-shadow: 0 20px 25px -5px rgba(15, 23, 42, 0.18);
            background: var(--card-bg);
            color: var(--text-main);
        }}
        dialog.files-modal::backdrop {{
            background: rgba(15, 23, 42, 0.45);
            backdrop-filter: blur(2px);
        }}
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 18px 24px;
            border-bottom: 1px solid var(--border);
        }}
        .modal-header h2 {{
            margin: 0;
            font-size: 1.2rem;
        }}
        .modal-close-btn {{
            background: #f1f5f9;
            border: none;
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 0.9rem;
            font-weight: 600;
            color: #334155;
            cursor: pointer;
        }}
        .modal-close-btn:hover {{
            background: #e2e8f0;
        }}
        .modal-body {{
            padding: 20px 24px;
            overflow-y: auto;
            max-height: calc(85vh - 75px);
        }}
        .modal-folder-info {{
            margin-bottom: 14px;
            font-size: 0.85rem;
            color: var(--text-muted);
            word-break: break-all;
        }}
        .file-name {{
            font-weight: 600;
            white-space: nowrap;
        }}
        .file-path code {{
            font-size: 0.78rem;
            color: var(--text-muted);
            word-break: break-all;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-left">
                <h1>{html.escape(title)}</h1>
                <div class="meta">Generated on {html.escape(summary.generated_at)} &bull; {html.escape(summary.agent_name)}</div>
            </div>
            <nav class="nav-pills">
                <a href="transactions.html" class="nav-pill active">1. BTA Transactions</a>
                <a href="balance.html" class="nav-pill">2. AA Balance Sheet</a>
            </nav>
        </header>

        <section class="summary-grid">
            <div class="card">
                <div>
                    <div class="card-label">Banks / Accounts</div>
                    <div class="card-value">{summary.banks_count} / {summary.bank_accounts_count}</div>
                </div>
                <div class="card-sub">Identified from PDFs</div>
            </div>

            <div class="card">
                <div>
                    <div class="card-label">PDF Files Read</div>
                    <div class="card-value">{summary.total_files_read}</div>
                </div>
                <div class="card-sub">
                    <a href="#read-files" class="modal-trigger-link" onclick="openFilesModal(event)">
                        View read files ({summary.total_files_read}) &nearr;
                    </a>
                </div>
            </div>

            <div class="card">
                <div>
                    <div class="card-label">Date Range (Start &rarr; End)</div>
                    <div class="card-value" style="font-size: 1.02rem;">{html.escape(summary.start_date)} &rarr; {html.escape(summary.end_date)}</div>
                </div>
                <div class="card-sub">Across all statements</div>
            </div>

            <div class="card">
                <div>
                    <div class="card-label">Unique Transactions</div>
                    <div class="card-value">{summary.unique_transactions_count}</div>
                </div>
                <div class="card-sub">
                    Raw: {summary.raw_transactions_count} &bull; Duplicates: {summary.duplicates_removed_count}
                </div>
            </div>

            <div class="card">
                <div>
                    <div class="card-label">Total Credits</div>
                    <div class="card-value amount-positive">+{summary.total_credits:,.2f} {html.escape(summary.currency)}</div>
                </div>
                <div class="card-sub">Incoming payments</div>
            </div>

            <div class="card">
                <div>
                    <div class="card-label">Total Debits</div>
                    <div class="card-value amount-negative">{summary.total_debits:,.2f} {html.escape(summary.currency)}</div>
                </div>
                <div class="card-sub">Outgoing payments</div>
            </div>

            <div class="card">
                <div>
                    <div class="card-label">Net Cashflow</div>
                    <div class="card-value {'amount-positive' if summary.net_cashflow >= 0 else 'amount-negative'}">{'+' if summary.net_cashflow > 0 else ''}{summary.net_cashflow:,.2f} {html.escape(summary.currency)}</div>
                </div>
                <div class="card-sub">Credits minus debits</div>
            </div>
        </section>

        <div class="toolbar">
            <input
                type="search"
                id="searchBox"
                class="search-input"
                placeholder="Filter by description, date, file, or amount..."
                oninput="filterRows()"
            />
            <a href="#read-files" class="modal-trigger-link" onclick="openFilesModal(event)">
                &#128194; Inspect {summary.total_files_read} Read PDF Files
            </a>
        </div>

        {sections_block}
    </div>

    <!-- Modal Window for Read PDF Files -->
    <dialog id="filesModal" class="files-modal" onclick="handleBackdropClick(event)">
        <div class="modal-header">
            <h2>Read Bank Statement PDF Files ({summary.total_files_read})</h2>
            <button type="button" class="modal-close-btn" onclick="closeFilesModal()">Close &times;</button>
        </div>
        <div class="modal-body">
            <div class="modal-folder-info">
                <strong>Source Folder:</strong> <code>{html.escape(summary.source_directory or "—")}</code>
            </div>
            <div class="table-wrapper" style="border-top: 1px solid var(--border); border-radius: 12px;">
                <table>
                    <thead>
                        <tr>
                            <th class="col-index">#</th>
                            <th>Filename</th>
                            <th>Bank</th>
                            <th>Bank Account</th>
                            <th>Filesystem Path</th>
                            <th style="text-align: right;">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {modal_files_block}
                    </tbody>
                </table>
            </div>
        </div>
    </dialog>

    <script>
        function filterRows() {{
            const query = document.getElementById("searchBox").value.toLowerCase();
            if (query.length > 0) {{
                document.querySelectorAll("details.account-section").forEach(d => d.open = true);
            }}
            const rows = document.querySelectorAll(".tx-row");
            rows.forEach(row => {{
                const text = row.innerText.toLowerCase();
                row.style.display = text.includes(query) ? "" : "none";
            }});
        }}

        function openFilesModal(event) {{
            if (event) event.preventDefault();
            const modal = document.getElementById("filesModal");
            if (modal && typeof modal.showModal === "function") {{
                modal.showModal();
            }}
        }}

        function closeFilesModal() {{
            const modal = document.getElementById("filesModal");
            if (modal) modal.close();
        }}

        function handleBackdropClick(event) {{
            const modal = document.getElementById("filesModal");
            if (event.target === modal) {{
                modal.close();
            }}
        }}
    </script>
</body>
</html>
"""


@tool
def generate_transactions_webpage(
    transactions: list[TransactionItem],
    output_path: str = "reports/transactions.html",
    open_browser: bool = True,
) -> str:
    """Identify Bank & Bank Account per transaction set, deduplicate, compute BTA counters, save JSON, and render HTML.

    Args:
        transactions: List of extracted transaction items (including bank_name and bank_account).
        output_path: File path where the HTML report should be saved (defaults to 'reports/transactions.html').
        open_browser: Whether to open the generated HTML file in the system web browser.
    """
    out_file = Path(output_path).expanduser().resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    _RAW_TRANSACTIONS.extend(transactions)

    report = build_bta_report(_RAW_TRANSACTIONS)
    html_content = build_transactions_html(report)
    out_file.write_text(html_content, encoding="utf-8")

    # Persist counters (summary), account_sets (grouped by Bank & Bank Account), and transactions to JSON
    json_cache = out_file.with_suffix(".json")
    json_cache.write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if open_browser and os.getenv("DISABLE_BROWSER_OPEN", "").lower() not in {"1", "true", "yes"}:
        try:
            webbrowser.open(out_file.as_uri())
        except Exception:
            pass

    s = report.summary
    sets_desc = ", ".join(
        f"{a.bank_name} [{a.bank_account}] ({a.transactions_count} txs)"
        for a in report.account_sets
    )
    return (
        f"Successfully generated webpage at {out_file} "
        f"(Files read: {s.total_files_read}, Period: {s.start_date} to {s.end_date}, "
        f"Raw transactions: {s.raw_transactions_count}, Unique: {s.unique_transactions_count}, "
        f"Duplicates removed: {s.duplicates_removed_count}, Account sets: {sets_desc})"
    )
