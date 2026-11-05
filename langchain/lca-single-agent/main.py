"""CLI entry point and 15-minute folder watcher for the Bank Transaction Agent (BTA)."""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from lca_single_agent.agent import build_single_agent
from lca_single_agent.tools import (
    TransactionItem,
    find_new_pdf_files,
    generate_transactions_webpage,
    list_pdf_files,
    load_existing_bta_state,
    reset_accumulated_transactions,
)


def rerender_from_cache(output_html: str = "reports/transactions.html") -> str:
    """Re-render the HTML webpage from cached reports/transactions.json without calling the LLM."""
    reset_accumulated_transactions()
    out_file = Path(output_html)
    json_cache = out_file.with_suffix(".json")
    if not json_cache.exists():
        raise FileNotFoundError(f"Cached transactions file not found at '{json_cache}'.")

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
    result = generate_transactions_webpage.invoke(
        {"transactions": items, "output_path": output_html, "open_browser": True}
    )
    print(result)
    return result


def run_agent_on_path(pdf_path: str, output_html: str = "reports/transactions.html") -> str:
    """Invoke the Bank Transaction Agent (BTA) on a directory or PDF file path."""
    reset_accumulated_transactions()
    resolved_target = Path(pdf_path).expanduser().resolve()
    os.environ["BANK_PDF_SOURCE_DIR"] = str(
        resolved_target if resolved_target.is_dir() else resolved_target.parent
    )
    agent = build_single_agent()

    user_prompt = (
        f"Please list and read all bank account PDF files from `{resolved_target}`, "
        f"extract and deduplicate all transactions, compute the BTA counters, and generate the HTML webpage at `{output_html}`."
    )
    print(f"Target path : {resolved_target}")
    print(f"Output HTML : {output_html}\n")

    response = agent.invoke({"messages": [{"role": "user", "content": user_prompt}]})
    messages = response.get("messages", [])
    final_text = messages[-1].content if messages else ""
    print("\n=== BTA Response ===")
    print(final_text)
    return final_text


def run_incremental_check(
    pdf_path: str,
    output_html: str = "reports/transactions.html",
    open_browser: bool = True,
) -> bool:
    """Check for newly added PDF files in pdf_path and process only new files if found.

    Returns:
        True if new PDF files were discovered and processed, False if no new files were found.
    """
    resolved_target = Path(pdf_path).expanduser().resolve()
    json_cache = Path(output_html).with_suffix(".json")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_pdfs, existing_count = find_new_pdf_files(resolved_target, json_cache)
    if not new_pdfs:
        print(
            f"[{now_str}] [BTA Watch] No new PDF files in '{resolved_target}' "
            f"({existing_count} file(s) already processed)."
        )
        return False

    print(
        f"[{now_str}] [BTA Watch] Found {len(new_pdfs)} new PDF file(s) "
        f"(already processed: {existing_count}): {[p.name for p in new_pdfs]}"
    )

    # Pre-load existing state so previously processed transactions are preserved
    load_existing_bta_state(resolved_target, json_cache)
    os.environ["BANK_PDF_SOURCE_DIR"] = str(
        resolved_target if resolved_target.is_dir() else resolved_target.parent
    )

    agent = build_single_agent()
    if len(new_pdfs) == 1:
        files_instruction = f"the new PDF file `{new_pdfs[0]}`"
    else:
        joined = ", ".join(f"`{p}`" for p in new_pdfs)
        files_instruction = f"these new PDF files: {joined}"

    user_prompt = (
        f"Please read {files_instruction} using `read_bank_statement_pdf`, "
        f"extract all transactions from the new file(s), and call `generate_transactions_webpage` "
        f"with `output_path='{output_html}'` and `open_browser={open_browser}`."
    )
    response = agent.invoke({"messages": [{"role": "user", "content": user_prompt}]})
    messages = response.get("messages", [])
    if messages:
        print(messages[-1].content)
    return True


def watch_folder_periodically(
    pdf_path: str,
    output_html: str = "reports/transactions.html",
    interval_minutes: float = 15.0,
) -> None:
    """Poll `pdf_path` for new PDF files every `interval_minutes` (default: 15 minutes)."""
    resolved_target = Path(pdf_path).expanduser().resolve()
    interval_seconds = max(1.0, interval_minutes * 60.0)
    print(
        f"=== BTA Watcher Started ===\n"
        f"Monitoring folder : {resolved_target}\n"
        f"Check interval    : every {interval_minutes:g} minute(s)\n"
        f"Press Ctrl+C to stop.\n"
    )
    try:
        while True:
            run_incremental_check(pdf_path=str(resolved_target), output_html=output_html)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\n[BTA Watch] Stopped folder monitoring.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bank Transaction Agent (BTA) — Read bank PDF statements, track counters, and render an HTML report."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Filesystem path to a folder containing bank statement PDFs (or a single PDF file).",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="reports/transactions.html",
        help="Output path for the generated HTML report (default: reports/transactions.html).",
    )
    parser.add_argument(
        "--rerender",
        action="store_true",
        help="Re-render the HTML report from cached reports/transactions.json without calling the LLM.",
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
        rerender_from_cache(args.output)
        return

    if not args.path:
        parser.print_help()
        return

    if args.watch:
        watch_folder_periodically(args.path, args.output, interval_minutes=args.interval)
        return

    run_agent_on_path(args.path, args.output)


if __name__ == "__main__":
    main()
