"""Agent 2: Accounting Agent (AA) definition using pure LangChain and LM Studio."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from lca_two_agents.tools import (
    generate_balance_webpage,
    read_bta_transactions_json,
)

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)

AA_SYSTEM_PROMPT = """You are Agent 2: the Accounting Agent (AA), built with pure LangChain.
Your goal is to read the transactions JSON file delivered by the Bank Transaction Agent (BTA) (`reports/transactions.json`) and create the **Balance** outcome webpage (`reports/balance.html`) containing the accounting balance table with `Date`, `Description`, `Incoming`, and `Expenses` columns.

Follow these steps carefully:
1. Call `read_bta_transactions_json` to inspect the transactions delivered by BTA.
2. Call `generate_balance_webpage` to build the Balance table separating each transaction into:
   - `date`: Transaction date (`YYYY-MM-DD`)
   - `description`: Clean accounting description of the income or expense
   - `incoming`: Positive amount for incoming payments/credits (or `0.0` for expenses)
   - `expense`: Positive amount for expenses/debits (or `0.0` for incoming payments)
   - `currency`: Currency code (`CHF`)
   - `source_file`: Source PDF filename
3. Reply with a brief accounting summary showing Total Incoming, Total Expenses, and Net Balance.
/no_think"""


def build_accounting_agent(
    model_name: str | None = None,
    base_url: str | None = None,
):
    """Create the Accounting Agent (AA) connected to LM Studio by default."""
    resolved_model = model_name or os.getenv("LM_STUDIO_MODEL", "qwen3.8-27b-uncensored-mlx")
    resolved_base_url = base_url or os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    api_key = os.getenv("LM_STUDIO_API_KEY", "lm-studio")

    model = init_chat_model(
        model=resolved_model,
        model_provider="openai",
        base_url=resolved_base_url,
        api_key=api_key,
        temperature=0.0,
        timeout=360,
        max_retries=2,
    )

    tools = [
        read_bta_transactions_json,
        generate_balance_webpage,
    ]

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=AA_SYSTEM_PROMPT,
    )


@tool
def notify_accounting_agent(
    bta_json_path: str = "reports/transactions.json",
    balance_output_path: str = "reports/balance.html",
    reason: str = "BTA discovered and parsed new bank statement file(s)",
) -> str:
    """Agent-to-Agent communication tool for BTA to notify the Accounting Agent (AA) to recalculate the Balance.

    Args:
        bta_json_path: Path to the updated BTA JSON file ('reports/transactions.json').
        balance_output_path: Path where AA should output the recalculated Balance webpage ('reports/balance.html').
        reason: Message from BTA explaining why the Balance recalculation is triggered.
    """
    print(f"\n[BTA -> AA Handoff] {reason}")
    aa_agent = build_accounting_agent()
    prompt = (
        f"Message from Bank Transaction Agent (BTA): '{reason}'. "
        f"Please read the updated transactions at `{bta_json_path}` and recalculate the Balance webpage at `{balance_output_path}`."
    )
    response = aa_agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    messages = response.get("messages", [])
    aa_reply = messages[-1].content if messages else "Balance recalculated."
    return f"Accounting Agent (AA) notified and completed Balance recalculation: {aa_reply}"
