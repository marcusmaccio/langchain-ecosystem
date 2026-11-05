"""Accounting Agent (AA) tools and schemas, reusing BTA from lca-single-agent and visualizing Balance per Bank and Bank Account."""

import html
import json
import os
import webbrowser
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool
from lca_single_agent.tools import (
    BankTransactionReport,
    ReadFileRecord,
    _register_pdf_path,
    normalize_date_str,
    resolve_pdf_path,
)
from pydantic import BaseModel, Field


class BalanceRow(BaseModel):
    """Schema for a single row in the Accounting Agent (AA) Balance Table."""

    date: str = Field(description="Transaction date in YYYY-MM-DD format")
    description: str = Field(
        description="Accounting description of the income or expense (including reference if useful)"
    )
    incoming: float = Field(
        default=0.0,
        description="Incoming (income/credit) amount as a positive number, or 0.0 if this is an expense",
    )
    expense: float = Field(
        default=0.0,
        description="Expense (debit/outgoing) amount as a positive number, or 0.0 if this is an income",
    )
    currency: str = Field(default="CHF", description="Currency code (e.g., CHF, EUR, USD)")
    bank_name: str = Field(default="", description="Name of the bank for this transaction")
    bank_account: str = Field(default="", description="Bank account / IBAN identifier for this transaction")
    source_file: str = Field(default="", description="Name or path of the source PDF file")


class AccountBalanceGroup(BaseModel):
    """Balance table and accounting totals for a single (Bank, Bank Account) pair."""

    bank_name: str
    bank_account: str
    currency: str = "CHF"
    start_date: str = "—"
    end_date: str = "—"
    total_entries: int = 0
    incoming_count: int = 0
    expenses_count: int = 0
    total_incoming: float = 0.0
    total_expenses: float = 0.0
    net_balance: float = 0.0
    entries: list[BalanceRow] = Field(default_factory=list)


class BalanceSummary(BaseModel):
    """Overall accounting counters and totals computed by the Accounting Agent (AA)."""

    agent_name: str = "Accounting Agent (AA)"
    source_directory: str = ""
    total_files_read: int = 0
    read_files: list[ReadFileRecord] = Field(default_factory=list)
    banks_count: int = 0
    bank_accounts_count: int = 0
    start_date: str = "—"
    end_date: str = "—"
    total_entries: int = 0
    incoming_count: int = 0
    expenses_count: int = 0
    total_incoming: float = 0.0
    total_expenses: float = 0.0
    net_balance: float = 0.0
    currency: str = "CHF"
    generated_at: str = ""


class BalanceReport(BaseModel):
    """Complete JSON payload persisted by AA to reports/balance.json."""

    summary: BalanceSummary
    account_balances: list[AccountBalanceGroup] = Field(default_factory=list)
    entries: list[BalanceRow] = Field(default_factory=list)


def _format_source_pdf_cell(source_file: str) -> str:
    """Format a Source PDF cell with a clickable file:// link using BTA's resolve_pdf_path."""
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


def _build_modal_html(read_files: list[ReadFileRecord], source_directory: str) -> str:
    """Build the <dialog> modal HTML for inspecting all read PDF files and their Bank/Account."""
    modal_file_rows: list[str] = []
    for f_idx, rf in enumerate(read_files, start=1):
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
    return f"""
    <dialog id="filesModal" class="files-modal" onclick="handleBackdropClick(event)">
        <div class="modal-header">
            <h2>Read Bank Statement PDF Files ({len(read_files)})</h2>
            <button type="button" class="modal-close-btn" onclick="closeFilesModal()">Close &times;</button>
        </div>
        <div class="modal-body">
            <div class="modal-folder-info">
                <strong>Source Folder:</strong> <code>{html.escape(source_directory or "—")}</code>
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
    </dialog>"""


def convert_bta_to_balance_report(
    bta_report: BankTransactionReport,
    custom_entries: list[BalanceRow] | None = None,
) -> BalanceReport:
    """Build a BalanceReport grouped by (Bank, Bank Account) from a BankTransactionReport produced by BTA."""
    file_bank_lookup: dict[str, tuple[str, str]] = {}
    for rf in bta_report.summary.read_files:
        if rf.file_path and Path(rf.file_path).exists():
            _register_pdf_path(Path(rf.file_path))
        if rf.file_name and (rf.bank_name or rf.bank_account):
            file_bank_lookup[rf.file_name] = (rf.bank_name, rf.bank_account)

    for acct_set in bta_report.account_sets:
        for tx in acct_set.transactions:
            fname = Path(tx.source_file).name if tx.source_file else ""
            if fname and fname not in file_bank_lookup:
                file_bank_lookup[fname] = (acct_set.bank_name, acct_set.bank_account)

    if custom_entries:
        entries: list[BalanceRow] = []
        for row in custom_entries:
            norm_date = normalize_date_str(row.date)
            inc = round(abs(row.incoming), 2) if row.incoming > 0 else 0.0
            exp = round(abs(row.expense), 2) if row.expense != 0 else 0.0
            fname = Path(row.source_file).name if row.source_file else ""
            fb_bank, fb_acct = file_bank_lookup.get(fname, ("", ""))
            b_name = row.bank_name.strip() or fb_bank or "Unknown Bank"
            b_acct = row.bank_account.strip() or fb_acct or "Default Account"
            entries.append(
                row.model_copy(
                    update={
                        "date": norm_date,
                        "incoming": inc,
                        "expense": exp,
                        "bank_name": b_name,
                        "bank_account": b_acct,
                    }
                )
            )
    else:
        entries = []
        source_txs = (
            [tx for acct_set in bta_report.account_sets for tx in acct_set.transactions]
            if bta_report.account_sets
            else bta_report.transactions
        )
        for tx in source_txs:
            desc = tx.description.strip()
            if tx.reference and tx.reference.strip() and tx.reference.strip() != "—":
                desc = f"{desc} ({tx.reference.strip()})"
            inc = round(tx.amount, 2) if tx.amount > 0 else 0.0
            exp = round(abs(tx.amount), 2) if tx.amount < 0 else 0.0
            fname = Path(tx.source_file).name if tx.source_file else ""
            fb_bank, fb_acct = file_bank_lookup.get(fname, ("", ""))
            b_name = tx.bank_name.strip() or fb_bank or "Unknown Bank"
            b_acct = tx.bank_account.strip() or fb_acct or "Default Account"
            entries.append(
                BalanceRow(
                    date=normalize_date_str(tx.date),
                    description=desc,
                    incoming=inc,
                    expense=exp,
                    currency=tx.currency,
                    bank_name=b_name,
                    bank_account=b_acct,
                    source_file=tx.source_file,
                )
            )

    entries.sort(key=lambda e: (e.bank_name, e.bank_account, e.date, Path(e.source_file).name))

    # Group entries by (bank_name, bank_account)
    grouped: dict[tuple[str, str], list[BalanceRow]] = {}
    for entry in entries:
        grouped.setdefault((entry.bank_name, entry.bank_account), []).append(entry)

    account_balances: list[AccountBalanceGroup] = []
    for (b_name, b_acct), group_entries in sorted(grouped.items(), key=lambda item: item[0]):
        group_entries.sort(key=lambda e: (e.date, Path(e.source_file).name))
        g_dates = sorted(e.date for e in group_entries if e.date)
        g_inc_count = sum(1 for e in group_entries if e.incoming > 0)
        g_exp_count = sum(1 for e in group_entries if e.expense > 0)
        g_inc_total = round(sum(e.incoming for e in group_entries), 2)
        g_exp_total = round(sum(e.expense for e in group_entries), 2)
        g_net = round(g_inc_total - g_exp_total, 2)
        g_curr = group_entries[0].currency if group_entries else "CHF"

        account_balances.append(
            AccountBalanceGroup(
                bank_name=b_name,
                bank_account=b_acct,
                currency=g_curr,
                start_date=g_dates[0] if g_dates else "—",
                end_date=g_dates[-1] if g_dates else "—",
                total_entries=len(group_entries),
                incoming_count=g_inc_count,
                expenses_count=g_exp_count,
                total_incoming=g_inc_total,
                total_expenses=g_exp_total,
                net_balance=g_net,
                entries=group_entries,
            )
        )

    incoming_count = sum(1 for e in entries if e.incoming > 0)
    expenses_count = sum(1 for e in entries if e.expense > 0)
    total_incoming = round(sum(e.incoming for e in entries), 2)
    total_expenses = round(sum(e.expense for e in entries), 2)
    net_balance = round(total_incoming - total_expenses, 2)

    dates = sorted(e.date for e in entries if e.date)
    start_date = dates[0] if dates else bta_report.summary.start_date
    end_date = dates[-1] if dates else bta_report.summary.end_date
    currency = entries[0].currency if entries else bta_report.summary.currency
    unique_banks = {g.bank_name for g in account_balances if g.bank_name}

    summary = BalanceSummary(
        source_directory=bta_report.summary.source_directory,
        total_files_read=bta_report.summary.total_files_read,
        read_files=bta_report.summary.read_files,
        banks_count=len(unique_banks),
        bank_accounts_count=len(account_balances),
        start_date=start_date,
        end_date=end_date,
        total_entries=len(entries),
        incoming_count=incoming_count,
        expenses_count=expenses_count,
        total_incoming=total_incoming,
        total_expenses=total_expenses,
        net_balance=net_balance,
        currency=currency,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    return BalanceReport(
        summary=summary,
        account_balances=account_balances,
        entries=entries,
    )


def build_balance_html(
    report: BalanceReport,
    title: str = "Accounting Agent (AA) — Balance per Bank & Account",
) -> str:
    """Generate the Accounting Agent (AA) Balance HTML webpage visualizing the Balance per Bank and Bank Account."""
    summary = report.summary
    modal_html = _build_modal_html(summary.read_files, summary.source_directory)
    net_class = "amount-positive" if summary.net_balance >= 0 else "amount-negative"
    net_prefix = "+" if summary.net_balance > 0 else ""

    # Render a dedicated Balance Section per (Bank, Bank Account)
    account_sections_html: list[str] = []
    for grp in report.account_balances:
        rows_html: list[str] = []
        for idx, entry in enumerate(grp.entries, start=1):
            if entry.incoming > 0:
                inc_cell = f'<td class="col-amount amount-positive">+{entry.incoming:,.2f} {html.escape(entry.currency)}</td>'
            else:
                inc_cell = '<td class="col-amount amount-zero">—</td>'

            if entry.expense > 0:
                exp_cell = f'<td class="col-amount amount-negative">-{entry.expense:,.2f} {html.escape(entry.currency)}</td>'
            else:
                exp_cell = '<td class="col-amount amount-zero">—</td>'

            source_cell = _format_source_pdf_cell(entry.source_file)

            rows_html.append(
                f"""
                <tr class="tx-row">
                    <td class="col-index">{idx}</td>
                    <td class="col-date">{html.escape(entry.date)}</td>
                    <td class="col-desc">{html.escape(entry.description)}</td>
                    {inc_cell}
                    {exp_cell}
                    <td class="col-source">{source_cell}</td>
                </tr>"""
            )

        rows_block = "\n".join(rows_html) if rows_html else (
            '<tr><td colspan="6" class="empty-row">No balance entries for this account.</td></tr>'
        )
        grp_net_cls = "amount-positive" if grp.net_balance >= 0 else "amount-negative"
        grp_net_pre = "+" if grp.net_balance > 0 else ""

        account_sections_html.append(
            f"""
            <details class="account-section">
                <summary class="account-banner">
                    <div class="account-banner-left">
                        <span class="bank-pill">&#127974; {html.escape(grp.bank_name)}</span>
                        <h2 class="account-title">{html.escape(grp.bank_account)}</h2>
                        <div class="account-period">
                            Accounting Period: <strong>{html.escape(grp.start_date)} &rarr; {html.escape(grp.end_date)}</strong>
                            &bull; {grp.total_entries} entries ({grp.incoming_count} incoming, {grp.expenses_count} expenses)
                        </div>
                    </div>
                    <div class="account-banner-right">
                        <div class="account-banner-stats">
                            <div class="mini-stat">
                                <span class="mini-label">Account Incoming</span>
                                <span class="mini-val amount-positive">+{grp.total_incoming:,.2f} {html.escape(grp.currency)}</span>
                            </div>
                            <div class="mini-stat">
                                <span class="mini-label">Account Expenses</span>
                                <span class="mini-val amount-negative">-{grp.total_expenses:,.2f} {html.escape(grp.currency)}</span>
                            </div>
                            <div class="mini-stat">
                                <span class="mini-label">Account Net Balance</span>
                                <span class="mini-val {grp_net_cls}">{grp_net_pre}{grp.net_balance:,.2f} {html.escape(grp.currency)}</span>
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
                                <th class="col-amount">Incoming</th>
                                <th class="col-amount">Expenses</th>
                                <th>Source PDF</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_block}
                        </tbody>
                        <tfoot>
                            <tr>
                                <td colspan="3" style="text-align: right;">
                                    Account Totals — {html.escape(grp.bank_name)} ({html.escape(grp.start_date)} &rarr; {html.escape(grp.end_date)})
                                </td>
                                <td class="col-amount amount-positive">+{grp.total_incoming:,.2f} {html.escape(grp.currency)}</td>
                                <td class="col-amount amount-negative">-{grp.total_expenses:,.2f} {html.escape(grp.currency)}</td>
                                <td></td>
                            </tr>
                            <tr>
                                <td colspan="3" style="text-align: right;">
                                    Account Net Balance (Incoming &minus; Expenses)
                                </td>
                                <td colspan="2" class="col-amount {grp_net_cls}" style="font-size: 1.08rem;">
                                    {grp_net_pre}{grp.net_balance:,.2f} {html.escape(grp.currency)}
                                </td>
                                <td></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            </details>"""
        )

    sections_block = "\n".join(account_sections_html) if account_sections_html else (
        '<div class="table-wrapper"><p class="empty-row">No account balances found.</p></div>'
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
            transition: all 0.15s ease;
        }}
        .nav-pill:hover {{
            border-color: var(--accent);
            color: var(--accent);
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
        tbody tr:hover td {{
            background: #f8fafc;
        }}
        tfoot td {{
            background: #f8fafc;
            font-weight: 700;
            border-top: 2px solid #cbd5e1;
        }}
        .col-index {{ color: var(--text-muted); width: 48px; }}
        .col-date {{ white-space: nowrap; font-variant-numeric: tabular-nums; width: 115px; }}
        .col-amount {{
            text-align: right;
            white-space: nowrap;
            font-weight: 600;
            font-variant-numeric: tabular-nums;
            width: 155px;
        }}
        th.col-amount {{ text-align: right; }}
        .amount-positive {{ color: var(--positive); }}
        .amount-negative {{ color: var(--negative); }}
        .amount-zero {{ color: #cbd5e1; font-weight: 400; }}
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
                <a href="transactions.html" class="nav-pill">1. BTA Transactions</a>
                <a href="balance.html" class="nav-pill active">2. AA Balance Sheet</a>
            </nav>
        </header>

        <section class="summary-grid">
            <div class="card">
                <div>
                    <div class="card-label">Banks / Accounts</div>
                    <div class="card-value">{summary.banks_count} / {summary.bank_accounts_count}</div>
                </div>
                <div class="card-sub">Balance per Bank &amp; Account</div>
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
                    <div class="card-label">Accounting Period</div>
                    <div class="card-value" style="font-size: 1.02rem;">{html.escape(summary.start_date)} &rarr; {html.escape(summary.end_date)}</div>
                </div>
                <div class="card-sub">{summary.total_entries} balance entries</div>
            </div>

            <div class="card">
                <div>
                    <div class="card-label">Total Incoming</div>
                    <div class="card-value amount-positive">+{summary.total_incoming:,.2f} {html.escape(summary.currency)}</div>
                </div>
                <div class="card-sub">{summary.incoming_count} income entries</div>
            </div>

            <div class="card">
                <div>
                    <div class="card-label">Total Expenses</div>
                    <div class="card-value amount-negative">-{summary.total_expenses:,.2f} {html.escape(summary.currency)}</div>
                </div>
                <div class="card-sub">{summary.expenses_count} expense entries</div>
            </div>

            <div class="card">
                <div>
                    <div class="card-label">Net Balance</div>
                    <div class="card-value {net_class}">{net_prefix}{summary.net_balance:,.2f} {html.escape(summary.currency)}</div>
                </div>
                <div class="card-sub">Incoming minus Expenses</div>
            </div>
        </section>

        <div class="toolbar">
            <input
                type="search"
                id="searchBox"
                class="search-input"
                placeholder="Filter balance by description, date, incoming, or expenses..."
                oninput="filterRows()"
            />
            <a href="#read-files" class="modal-trigger-link" onclick="openFilesModal(event)">
                &#128194; Inspect {summary.total_files_read} Read PDF Files
            </a>
        </div>

        {sections_block}
    </div>
    {modal_html}
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


def _load_bta_report_from_json(json_path: str = "reports/transactions.json") -> BankTransactionReport:
    """Load the BankTransactionReport JSON produced by BTA."""
    in_file = Path(json_path).expanduser().resolve()
    if not in_file.exists():
        raise FileNotFoundError(f"BTA JSON file not found at '{in_file}'.")

    raw_data = json.loads(in_file.read_text(encoding="utf-8"))
    return BankTransactionReport(**raw_data)


@tool
def read_bta_transactions_json(json_path: str = "reports/transactions.json") -> str:
    """Read the transactions JSON file delivered by the Bank Transaction Agent (BTA), grouped by Bank and Bank Account.

    Args:
        json_path: Path to the BTA JSON file (defaults to 'reports/transactions.json').
    """
    try:
        report = _load_bta_report_from_json(json_path)
    except Exception as exc:
        return f"Error loading BTA JSON '{json_path}': {exc}"

    lines = [
        f"Loaded BTA Report ({report.summary.unique_transactions_count} unique transactions, "
        f"period {report.summary.start_date} to {report.summary.end_date}, "
        f"banks: {report.summary.banks_count}, accounts: {report.summary.bank_accounts_count}):"
    ]
    for acct_set in report.account_sets:
        lines.append(
            f"\n=== BANK: {acct_set.bank_name} | ACCOUNT: {acct_set.bank_account} "
            f"({acct_set.transactions_count} txs) ==="
        )
        for idx, tx in enumerate(acct_set.transactions, start=1):
            kind = "INCOMING" if tx.amount > 0 else "EXPENSE"
            lines.append(
                f"  {idx}. [{kind}] date={tx.date} | amount={tx.amount:.2f} {tx.currency} | "
                f"description={tx.description} | ref={tx.reference} | source_file={Path(tx.source_file).name}"
            )
    return "\n".join(lines)


@tool
def generate_balance_webpage(
    entries: list[BalanceRow] | None = None,
    bta_json_path: str = "reports/transactions.json",
    output_path: str = "reports/balance.html",
    open_browser: bool = True,
) -> str:
    """Create the Balance webpage per Bank and Bank Account (with Date, Description, Incoming, Expenses columns) and save reports/balance.json.

    Args:
        entries: Optional list of BalanceRow items prepared by the Accounting Agent. If omitted, derived automatically from the BTA JSON file.
        bta_json_path: Path to the BTA JSON file (defaults to 'reports/transactions.json').
        output_path: File path where the Balance HTML page should be saved (defaults to 'reports/balance.html').
        open_browser: Whether to open the generated Balance HTML file in the browser.
    """
    out_file = Path(output_path).expanduser().resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    bta_report = _load_bta_report_from_json(bta_json_path)
    balance_report = convert_bta_to_balance_report(bta_report, custom_entries=entries)

    html_content = build_balance_html(balance_report)
    out_file.write_text(html_content, encoding="utf-8")

    balance_json = out_file.with_suffix(".json")
    balance_json.write_text(
        json.dumps(balance_report.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if open_browser and os.getenv("DISABLE_BROWSER_OPEN", "").lower() not in {"1", "true", "yes"}:
        try:
            webbrowser.open(out_file.as_uri())
        except Exception:
            pass

    s = balance_report.summary
    accts_summary = ", ".join(
        f"{g.bank_name} [{g.bank_account}]: Net {g.net_balance:+,.2f} {g.currency}"
        for g in balance_report.account_balances
    )
    return (
        f"Successfully generated Balance webpage at {out_file} "
        f"(Banks: {s.banks_count}, Accounts: {s.bank_accounts_count}, Entries: {s.total_entries}, "
        f"Incoming: +{s.total_incoming:,.2f} {s.currency}, "
        f"Expenses: -{s.total_expenses:,.2f} {s.currency}, Net Balance: {s.net_balance:+,.2f} {s.currency} | {accts_summary})"
    )
