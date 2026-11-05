"""Bank Transaction Agent (BTA) definition using pure LangChain and LM Studio."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from lca_single_agent.tools import (
    generate_transactions_webpage,
    list_pdf_files,
    read_bank_statement_pdf,
)

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)

SYSTEM_PROMPT = """You are the Bank Transaction Agent (BTA), built with pure LangChain.
Your goal is to read bank statement PDF files from a user-provided filesystem path, track file and transaction counters, deduplicate transactions, persist the counters and transactions to JSON, and generate an interactive HTML webpage.

Follow these steps carefully:
1. Call `list_pdf_files` on the user-provided directory (or file) path to discover all PDF files, count them, and register their paths in memory.
2. Call `read_bank_statement_pdf` on the directory (or file) path to read the statement text of all discovered PDF files.
3. Extract EVERY transaction across ALL statements, recording:
   - `date`: Transaction or booking date in `YYYY-MM-DD` format
   - `description`: Counterparty / merchant / transaction details
   - `amount`: Numeric amount (negative for debits/withdrawals/payments, positive for credits/deposits/incoming transfers)
   - `currency`: Currency code (e.g. CHF, EUR, USD)
   - `reference`: Optional booking reference or category if present
   - `bank_name`: Name of the Bank identified from the PDF statement (e.g. "Banque Migros SA")
   - `bank_account`: Bank Account identifier / IBAN / account label from the PDF statement
   - `source_file`: The PDF filename the transaction came from
4. Call `generate_transactions_webpage` with the extracted transactions. This tool automatically:
   - Computes the start date and end date across all transactions
   - Records the raw transaction count, deduplicates transactions, and records the unique transaction count
   - Stores all counters, read file paths, and unique transactions into `reports/transactions.json`
   - Renders `reports/transactions.html` with the BTA counter cards and the modal window of read files
5. Reply with a summary of the BTA counters (files read, date range, raw vs. unique transaction counts, and output paths).
/no_think"""


def build_single_agent(
    model_name: str | None = None,
    base_url: str | None = None,
    extra_tools: list | None = None,
):
    """Create the Bank Transaction Agent (BTA) connected to LM Studio by default."""
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
        list_pdf_files,
        read_bank_statement_pdf,
        generate_transactions_webpage,
    ]
    prompt = SYSTEM_PROMPT
    if extra_tools:
        tools.extend(extra_tools)
        prompt = SYSTEM_PROMPT.replace(
            "5. Reply with a summary",
            "5. If `notify_accounting_agent` is available, call `notify_accounting_agent` to communicate with the Accounting Agent (AA) and trigger a recalculation of the Balance.\n6. Reply with a summary",
        )

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=prompt,
    )
