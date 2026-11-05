# Bank Transaction Agent (BTA) — Single Agent (`lca-single-agent`)

> **Full Conceptual & Architectural Documentation**:
> - [Stage 1 Learning Guide (`docs/langchain/lca-single-agent/README.md`)](../../docs/langchain/lca-single-agent/README.md)
> - [Stage 1 Architecture Deep Dive (`docs/langchain/lca-single-agent/architecture.md`)](../../docs/langchain/lca-single-agent/architecture.md)

## Project Details

`lca-single-agent` implements the **Bank Transaction Agent (BTA)** using pure **LangChain v1.x** (`create_agent`) and **LM Studio** (`qwen3.8-27b-uncensored-mlx`).

- **Standalone by Default**: Calling `build_single_agent()` (`extra_tools=None`) runs BTA as a 100% self-contained single agent with its 3 core tools (`list_pdf_files`, `read_bank_statement_pdf`, `generate_transactions_webpage`).
- **Packaged for Reuse**: Exported as the editable package `lca_single_agent` so [`../lca-two-agents`](../lca-two-agents) and [`../../langgraph/lca-langgraph-agents`](../../langgraph/lca-langgraph-agents) reuse BTA with zero code duplication.
- **Outputs**:
  - [`reports/transactions.json`](reports/transactions.json): BTA counters (`total_files_read`, `read_files`, `banks_identified`, `bank_accounts_identified`, `start_date`, `end_date`, `raw_transactions_count`, `unique_transactions_count`, `duplicates_removed_count`), per-account sets (`account_sets`), and unique transactions.
  - [`reports/transactions.html`](reports/transactions.html): Expandable per-account transaction tables (`<details>`), summary counter cards, and a `<dialog>` modal window listing all read PDF files.

---

## Project Layout

```text
lca-single-agent/
├── .env.example
├── pyproject.toml          # Exports editable package `lca_single_agent`
├── main.py                 # Standalone CLI + 15-minute folder watcher (--watch) + --rerender
├── reports/
│   ├── transactions.json
│   └── transactions.html
├── src/
│   ├── agent.py            # build_single_agent(extra_tools=None)
│   └── tools.py            # Pydantic schemas, PDF reader, deduplication & HTML renderer
└── tests/
    └── test_agent.py       # Unit tests for BTA tools, counters, and incremental watcher
```

---

## CLI Usage

```bash
cd /Users/marcomaccio/Documents/development/personal/langchain-ecosystem/langchain/lca-single-agent

# 1. Run BTA standalone on a folder of bank statement PDFs:
uv run python main.py "/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"

# 2. Watch folder every 15 minutes for newly added PDFs:
uv run python main.py --watch "/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"

# 3. Re-render HTML layout from cached JSON (<0.1s, no LLM call):
uv run python main.py --rerender

# 4. Run unit tests & linter:
uv run pytest -v
uv run ruff check .
```
