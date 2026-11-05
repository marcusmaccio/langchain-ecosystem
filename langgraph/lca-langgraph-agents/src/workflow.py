"""LangGraph StateGraph coordinating Agent 1 (BTA) and Agent 2 (Accounting Agent)."""

import operator
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from lca_single_agent.agent import build_single_agent as build_bta_agent
from lca_single_agent.tools import (
    find_new_pdf_files,
    load_existing_bta_state,
    reset_accumulated_transactions,
)
from lca_two_agents.accounting_agent import build_accounting_agent


class WorkflowState(TypedDict, total=False):
    """Shared state passed across the LangGraph nodes coordinating BTA and AA."""

    pdf_path: str
    bta_html_path: str
    bta_json_path: str
    balance_html_path: str
    balance_json_path: str
    incremental: bool
    open_browser: bool
    new_files: list[str]
    existing_files_count: int
    should_process: bool
    bta_response: str
    aa_response: str
    workflow_steps: Annotated[list[str], operator.add]


def discover_files_node(state: WorkflowState) -> WorkflowState:
    """Node 1: Inspect the target path and determine whether BTA should run."""
    pdf_path = Path(state["pdf_path"]).expanduser().resolve()
    bta_html_path = state.get("bta_html_path", "reports/transactions.html")
    bta_json_path = str(Path(bta_html_path).with_suffix(".json"))
    balance_html_path = state.get("balance_html_path", "reports/balance.html")
    balance_json_path = str(Path(balance_html_path).with_suffix(".json"))
    incremental = bool(state.get("incremental", False))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if incremental:
        new_pdfs, existing_count = find_new_pdf_files(pdf_path, Path(bta_json_path))
        if not new_pdfs:
            msg = (
                f"[{now_str}] [LangGraph: discover_files] No new PDF files in '{pdf_path}' "
                f"({existing_count} file(s) already processed). Skipping BTA & AA."
            )
            print(msg)
            return {
                "pdf_path": str(pdf_path),
                "bta_html_path": bta_html_path,
                "bta_json_path": bta_json_path,
                "balance_html_path": balance_html_path,
                "balance_json_path": balance_json_path,
                "new_files": [],
                "existing_files_count": existing_count,
                "should_process": False,
                "workflow_steps": [msg],
            }

        msg = (
            f"[{now_str}] [LangGraph: discover_files] Discovered {len(new_pdfs)} new PDF file(s): "
            f"{[p.name for p in new_pdfs]} (already processed: {existing_count}). Routing to BTA."
        )
        print(msg)
        return {
            "pdf_path": str(pdf_path),
            "bta_html_path": bta_html_path,
            "bta_json_path": bta_json_path,
            "balance_html_path": balance_html_path,
            "balance_json_path": balance_json_path,
            "new_files": [str(p) for p in new_pdfs],
            "existing_files_count": existing_count,
            "should_process": True,
            "workflow_steps": [msg],
        }

    # Full run mode: discover all PDFs in folder or single PDF
    pdfs = (
        sorted(p.resolve() for p in pdf_path.glob("*.pdf") if p.is_file())
        if pdf_path.is_dir()
        else ([pdf_path] if pdf_path.exists() else [])
    )
    should_process = len(pdfs) > 0
    msg = (
        f"[{now_str}] [LangGraph: discover_files] Full scan found {len(pdfs)} PDF file(s) at '{pdf_path}'."
    )
    print(msg)
    return {
        "pdf_path": str(pdf_path),
        "bta_html_path": bta_html_path,
        "bta_json_path": bta_json_path,
        "balance_html_path": balance_html_path,
        "balance_json_path": balance_json_path,
        "new_files": [str(p) for p in pdfs],
        "existing_files_count": 0,
        "should_process": should_process,
        "workflow_steps": [msg],
    }


def route_after_discovery(
    state: WorkflowState,
) -> Literal["bta_node", "__end__"]:
    """Conditional edge: route to BTA only when there are PDF files to process."""
    if state.get("should_process", False):
        return "bta_node"
    return "__end__"


def bta_node(state: WorkflowState) -> WorkflowState:
    """Node 2: Execute Agent 1 — Bank Transaction Agent (reused from lca-single-agent)."""
    resolved_target = Path(state["pdf_path"]).expanduser().resolve()
    bta_html = state.get("bta_html_path", "reports/transactions.html")
    bta_json = state.get("bta_json_path", str(Path(bta_html).with_suffix(".json")))
    incremental = bool(state.get("incremental", False))
    open_browser = bool(state.get("open_browser", False))

    os.environ["BANK_PDF_SOURCE_DIR"] = str(
        resolved_target if resolved_target.is_dir() else resolved_target.parent
    )

    if incremental:
        load_existing_bta_state(resolved_target, Path(bta_json))
        new_files = state.get("new_files", [])
        joined = ", ".join(f"`{p}`" for p in new_files)
        bta_prompt = (
            f"Please read these new PDF files using `read_bank_statement_pdf`: {joined}, "
            f"extract all transactions from them, and call `generate_transactions_webpage` "
            f"with `output_path='{bta_html}'` and `open_browser={open_browser}`."
        )
    else:
        reset_accumulated_transactions()
        bta_prompt = (
            f"List and read all bank account PDF files from `{resolved_target}`, "
            f"extract and deduplicate all transactions, compute the BTA counters, "
            f"and call `generate_transactions_webpage` with `output_path='{bta_html}'` and `open_browser={open_browser}`."
        )

    print("\n--- [LangGraph Node: bta_node] Running Agent 1: Bank Transaction Agent (BTA) ---")
    # Note: BTA runs in pure standalone configuration here; LangGraph itself coordinates the transition to AA!
    bta_agent = build_bta_agent()
    response = bta_agent.invoke({"messages": [{"role": "user", "content": bta_prompt}]})
    messages = response.get("messages", [])
    final_text = messages[-1].content if messages else ""
    print("\n=== BTA Node Output ===")
    print(final_text)

    return {
        "bta_response": final_text,
        "workflow_steps": [f"bta_node: generated {bta_json} and {bta_html}"],
    }


def route_after_bta(
    state: WorkflowState,
) -> Literal["aa_node", "__end__"]:
    """Conditional edge: route to Accounting Agent (AA) once BTA has delivered transactions.json."""
    bta_json = Path(state.get("bta_json_path", "reports/transactions.json"))
    if bta_json.exists():
        return "aa_node"
    return "__end__"


def aa_node(state: WorkflowState) -> WorkflowState:
    """Node 3: Execute Agent 2 — Accounting Agent (reused from lca-two-agents)."""
    bta_json = state.get("bta_json_path", "reports/transactions.json")
    balance_html = state.get("balance_html_path", "reports/balance.html")

    print("\n--- [LangGraph Node: aa_node] Running Agent 2: Accounting Agent (AA) ---")
    aa_agent = build_accounting_agent()
    aa_prompt = (
        f"Read the BTA transactions from `{bta_json}` and create the Balance webpage at `{balance_html}` "
        "with Date, Description, Incoming, and Expenses columns grouped by Bank and Bank Account."
    )
    response = aa_agent.invoke({"messages": [{"role": "user", "content": aa_prompt}]})
    messages = response.get("messages", [])
    final_text = messages[-1].content if messages else ""
    print("\n=== AA Node Output ===")
    print(final_text)

    return {
        "aa_response": final_text,
        "workflow_steps": [f"aa_node: generated {balance_html}"],
    }


def build_bta_aa_graph():
    """Construct and compile the LangGraph StateGraph coordinating BTA and AA."""
    builder = StateGraph(WorkflowState)

    # Register graph nodes
    builder.add_node("discover_files", discover_files_node)
    builder.add_node("bta_node", bta_node)
    builder.add_node("aa_node", aa_node)

    # Wire graph edges and conditional routing
    builder.add_edge(START, "discover_files")
    builder.add_conditional_edges(
        "discover_files",
        route_after_discovery,
        {
            "bta_node": "bta_node",
            "__end__": END,
        },
    )
    builder.add_conditional_edges(
        "bta_node",
        route_after_bta,
        {
            "aa_node": "aa_node",
            "__end__": END,
        },
    )
    builder.add_edge("aa_node", END)

    return builder.compile()


def get_graph_mermaid() -> str:
    """Return the Mermaid diagram representation of the compiled LangGraph workflow."""
    graph = build_bta_aa_graph()
    return graph.get_graph().draw_mermaid()
