"""CLI orchestrator for the two-agent pipeline: reuses BTA from lca-single-agent -> Accounting Agent (AA)."""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from lca_single_agent.agent import build_single_agent as build_bta_agent
from lca_single_agent.tools import (
    TransactionItem,
    find_new_pdf_files,
    generate_transactions_webpage,
    list_pdf_files,
    load_existing_bta_state,
    reset_accumulated_transactions,
)
from lca_two_agents.accounting_agent import (
    build_accounting_agent,
    notify_accounting_agent,
)
from lca_two_agents.tools import generate_balance_webpage


def rerender_from_cache(
    bta_html: str = "reports/transactions.html",
    balance_html: str = "reports/balance.html",
) -> None:
    """Re-render both the BTA Transactions page and the AA Balance page from reports/transactions.json without calling the LLM."""
    reset_accumulated_transactions()
    bta_out = Path(bta_html)
    json_cache = bta_out.with_suffix(".json")
    if not json_cache.exists():
        raise FileNotFoundError(f"Cached BTA JSON file not found at '{json_cache}'.")

    raw_data = json.loads(json_cache.read_text(encoding="utf-8"))
    if isinstance(raw_data, dict):
        summary_data = raw_data.get("summary", {})
        source_dir = summary_data.get("source_directory", "")
        if source_dir and Path(source_dir).exists():
            os.environ["BANK_PDF_SOURCE_DIR"] = source_dir
            list_pdf_files.invoke({"path": source_dir})
        raw_items = raw_data.get("transactions", [])
    else:
        raw_items = raw_data

    items = [TransactionItem(**item).model_dump() for item in raw_items]
    bta_res = generate_transactions_webpage.invoke(
        {"transactions": items, "output_path": bta_html, "open_browser": False}
    )
    print(bta_res)

    aa_res = generate_balance_webpage.invoke(
        {
            "bta_json_path": str(json_cache),
            "output_path": balance_html,
            "open_browser": True,
        }
    )
    print(aa_res)


def run_accounting_agent(
    bta_json: str = "reports/transactions.json",
    balance_html: str = "reports/balance.html",
) -> str:
    """Invoke Agent 2: Accounting Agent (AA) on the JSON file produced by BTA."""
    aa_agent = build_accounting_agent()
    prompt = (
        f"Read the BTA transactions from `{bta_json}` and create the Balance webpage at `{balance_html}` "
        "with Date, Description, Incoming, and Expenses columns."
    )
    print("\n--- Running Agent 2: Accounting Agent (AA) ---")
    response = aa_agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    messages = response.get("messages", [])
    final_text = messages[-1].content if messages else ""
    print("\n=== Accounting Agent (AA) Response ===")
    print(final_text)
    return final_text


def run_bta_standalone(
    pdf_path: str,
    bta_html: str = "reports/transactions.html",
) -> str:
    """Invoke Agent 1 (BTA) standalone without AA handoff."""
    reset_accumulated_transactions()
    resolved_target = Path(pdf_path).expanduser().resolve()
    os.environ["BANK_PDF_SOURCE_DIR"] = str(
        resolved_target if resolved_target.is_dir() else resolved_target.parent
    )
    bta_agent = build_bta_agent()
    bta_prompt = (
        f"List and read all bank account PDF files from `{resolved_target}`, "
        f"extract and deduplicate all transactions, compute the BTA counters, and deliver `{bta_html}` and its JSON file."
    )
    print("--- Running Agent 1 Standalone: Bank Transaction Agent (BTA) ---")
    print(f"Target path : {resolved_target}")
    bta_response = bta_agent.invoke({"messages": [{"role": "user", "content": bta_prompt}]})
    bta_messages = bta_response.get("messages", [])
    final_text = bta_messages[-1].content if bta_messages else ""
    print("\n=== Bank Transaction Agent (BTA) Response ===")
    print(final_text)
    return final_text


def run_two_agent_pipeline(
    pdf_path: str,
    bta_html: str = "reports/transactions.html",
    balance_html: str = "reports/balance.html",
) -> None:
    """Run Agent 1 (BTA imported from lca-single-agent), then hand off reports/transactions.json to Agent 2 (AA)."""
    reset_accumulated_transactions()
    resolved_target = Path(pdf_path).expanduser().resolve()
    os.environ["BANK_PDF_SOURCE_DIR"] = str(
        resolved_target if resolved_target.is_dir() else resolved_target.parent
    )

    # Step 1: Bank Transaction Agent (BTA) imported from lca-single-agent, equipped with notify_accounting_agent tool
    bta_agent = build_bta_agent(extra_tools=[notify_accounting_agent])
    bta_prompt = (
        f"List and read all bank account PDF files from `{resolved_target}`, "
        f"extract and deduplicate all transactions, compute the BTA counters, deliver `{bta_html}` and its JSON file, "
        f"and then call `notify_accounting_agent` to trigger the Accounting Agent (AA) to recalculate `{balance_html}`."
    )
    print("--- Running Agent 1: Bank Transaction Agent (BTA from lca-single-agent) ---")
    print(f"Target path : {resolved_target}")
    bta_response = bta_agent.invoke({"messages": [{"role": "user", "content": bta_prompt}]})
    bta_messages = bta_response.get("messages", [])
    if bta_messages:
        print("\n=== Bank Transaction Agent (BTA) Response ===")
        print(bta_messages[-1].content)

    # Fallback check: if BTA did not invoke notify_accounting_agent directly during tool calling, trigger AA
    tool_calls_made = [
        tc.get("name")
        for m in bta_messages
        for tc in (getattr(m, "tool_calls", None) or [])
    ]
    if "notify_accounting_agent" not in tool_calls_made:
        bta_json = str(Path(bta_html).with_suffix(".json"))
        run_accounting_agent(bta_json=bta_json, balance_html=balance_html)


def watch_two_agent_pipeline(
    pdf_path: str,
    bta_html: str = "reports/transactions.html",
    balance_html: str = "reports/balance.html",
    interval_minutes: float = 15.0,
) -> None:
    """Poll `pdf_path` every `interval_minutes` (default 15m); when BTA finds new PDFs, update both BTA and AA Balance."""
    resolved_target = Path(pdf_path).expanduser().resolve()
    json_cache = Path(bta_html).with_suffix(".json")
    interval_seconds = max(1.0, interval_minutes * 60.0)

    print(
        f"=== Two-Agent Watcher (BTA -> AA) Started ===\n"
        f"Monitoring folder : {resolved_target}\n"
        f"Check interval    : every {interval_minutes:g} minute(s)\n"
        f"Press Ctrl+C to stop.\n"
    )
    try:
        while True:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_pdfs, existing_count = find_new_pdf_files(resolved_target, json_cache)
            if not new_pdfs:
                print(
                    f"[{now_str}] [BTA Watch] No new PDF files in '{resolved_target}' "
                    f"({existing_count} file(s) already processed)."
                )
            else:
                print(
                    f"[{now_str}] [BTA Watch] Found {len(new_pdfs)} new PDF file(s): "
                    f"{[p.name for p in new_pdfs]}"
                )
                load_existing_bta_state(resolved_target, json_cache)
                os.environ["BANK_PDF_SOURCE_DIR"] = str(
                    resolved_target if resolved_target.is_dir() else resolved_target.parent
                )
                bta_agent = build_bta_agent(extra_tools=[notify_accounting_agent])
                joined = ", ".join(f"`{p}`" for p in new_pdfs)
                bta_prompt = (
                    f"Please read these new PDF files using `read_bank_statement_pdf`: {joined}, "
                    f"extract all transactions from them, call `generate_transactions_webpage` "
                    f"with `output_path='{bta_html}'` and `open_browser=False`, and then call `notify_accounting_agent` "
                    f"to communicate with the Accounting Agent (AA) to recalculate the Balance at `{balance_html}`."
                )
                bta_resp = bta_agent.invoke({"messages": [{"role": "user", "content": bta_prompt}]})
                bta_msgs = bta_resp.get("messages", [])
                called_tools = [
                    tc.get("name")
                    for m in bta_msgs
                    for tc in (getattr(m, "tool_calls", None) or [])
                ]
                if "notify_accounting_agent" not in called_tools:
                    run_accounting_agent(bta_json=str(json_cache), balance_html=balance_html)

            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\n[BTA -> AA Watch] Stopped folder monitoring.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Two-Agent Pipeline: Bank Transaction Agent (BTA from lca-single-agent) -> Accounting Agent (AA)."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Filesystem path to a folder containing bank statement PDFs (or a single PDF file).",
    )
    parser.add_argument(
        "--bta-only",
        action="store_true",
        help="Run only Agent 1 (Bank Transaction Agent) standalone without triggering the Accounting Agent.",
    )
    parser.add_argument(
        "--aa-only",
        action="store_true",
        help="Run only Agent 2 (Accounting Agent) using existing reports/transactions.json.",
    )
    parser.add_argument(
        "--rerender",
        action="store_true",
        help="Re-render both transactions.html and balance.html from cached reports/transactions.json without calling the LLM.",
    )
    parser.add_argument(
        "--watch",
        "-w",
        action="store_true",
        help="Continuously check the folder for new PDF files every 15 minutes (or --interval).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="Polling interval in minutes when using --watch (default: 15).",
    )
    args = parser.parse_args()

    if args.rerender:
        rerender_from_cache()
        return

    if args.aa_only:
        run_accounting_agent()
        return

    if not args.path:
        parser.print_help()
        return

    if args.bta_only:
        run_bta_standalone(args.path)
        return

    if args.watch:
        watch_two_agent_pipeline(args.path, interval_minutes=args.interval)
        return

    run_two_agent_pipeline(args.path)


if __name__ == "__main__":
    main()
