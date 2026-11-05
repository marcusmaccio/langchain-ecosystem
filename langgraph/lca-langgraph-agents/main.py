"""CLI entry point for the LangGraph StateGraph coordinating BTA and Accounting Agent (AA)."""

import argparse
import json
import os
import time
from pathlib import Path

from lca_langgraph.workflow import build_bta_aa_graph, get_graph_mermaid
from lca_single_agent.tools import (
    TransactionItem,
    generate_transactions_webpage,
    list_pdf_files,
    reset_accumulated_transactions,
)
from lca_two_agents.tools import generate_balance_webpage


def rerender_from_cache(
    bta_html: str = "reports/transactions.html",
    balance_html: str = "reports/balance.html",
    open_browser: bool = True,
) -> None:
    """Re-render both BTA transactions.html and AA balance.html from cached reports/transactions.json without calling the LLM."""
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
            "open_browser": open_browser,
        }
    )
    print(aa_res)


def run_langgraph_workflow(
    pdf_path: str,
    bta_html: str = "reports/transactions.html",
    balance_html: str = "reports/balance.html",
    incremental: bool = False,
) -> dict:
    """Invoke the compiled LangGraph StateGraph (discover_files -> bta_node -> aa_node)."""
    graph = build_bta_aa_graph()
    initial_state = {
        "pdf_path": str(Path(pdf_path).expanduser().resolve()),
        "bta_html_path": bta_html,
        "bta_json_path": str(Path(bta_html).with_suffix(".json")),
        "balance_html_path": balance_html,
        "balance_json_path": str(Path(balance_html).with_suffix(".json")),
        "incremental": incremental,
        "open_browser": False,
        "workflow_steps": [],
    }
    final_state = graph.invoke(initial_state)
    print("\n=== LangGraph Workflow Execution Trace ===")
    for idx, step in enumerate(final_state.get("workflow_steps", []), start=1):
        print(f"  {idx}. {step}")
    return final_state


def watch_langgraph_workflow(
    pdf_path: str,
    bta_html: str = "reports/transactions.html",
    balance_html: str = "reports/balance.html",
    interval_minutes: float = 15.0,
) -> None:
    """Trigger the LangGraph workflow in incremental mode every `interval_minutes` (default 15 minutes)."""
    resolved_target = Path(pdf_path).expanduser().resolve()
    interval_seconds = max(1.0, interval_minutes * 60.0)
    print(
        f"=== LangGraph Watcher (discover_files -> BTA -> AA) Started ===\n"
        f"Monitoring folder : {resolved_target}\n"
        f"Check interval    : every {interval_minutes:g} minute(s)\n"
        f"Press Ctrl+C to stop.\n"
    )
    try:
        while True:
            run_langgraph_workflow(
                pdf_path=str(resolved_target),
                bta_html=bta_html,
                balance_html=balance_html,
                incremental=True,
            )
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\n[LangGraph Watch] Stopped folder monitoring.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LangGraph StateGraph Workflow coordinating the Bank Transaction Agent (BTA) and Accounting Agent (AA)."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Filesystem path to a folder containing bank statement PDFs (or a single PDF file).",
    )
    parser.add_argument(
        "--graph",
        action="store_true",
        help="Print the compiled LangGraph Mermaid state diagram and exit.",
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
        help="Continuously run the LangGraph workflow in incremental mode every 15 minutes (or --interval).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="Polling interval in minutes when using --watch (default: 15).",
    )
    args = parser.parse_args()

    if args.graph:
        print(get_graph_mermaid())
        return

    if args.rerender:
        rerender_from_cache()
        return

    if not args.path:
        parser.print_help()
        return

    if args.watch:
        watch_langgraph_workflow(args.path, interval_minutes=args.interval)
        return

    run_langgraph_workflow(args.path, incremental=False)


if __name__ == "__main__":
    main()
