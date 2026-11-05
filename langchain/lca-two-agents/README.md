# Two-Agent Pipeline — Reused BTA + Accounting Agent (`lca-two-agents`)

> **Full Conceptual & Architectural Documentation**:
> - [Stage 2 Learning Guide (`docs/langchain/lca-two-agents/README.md`)](../../docs/langchain/lca-two-agents/README.md)
> - [Stage 2 Architecture Deep Dive (`docs/langchain/lca-two-agents/architecture.md`)](../../docs/langchain/lca-two-agents/architecture.md)

## Project Details

`lca-two-agents` implements a **Two-Agent Pipeline in pure LangChain v1.x** with **zero code duplication**:

1. **Agent 1 — Bank Transaction Agent (BTA)**: Reused directly from [`../lca-single-agent`](../lca-single-agent) as an editable dependency (`lca_single_agent`).
2. **Agent 2 — Accounting Agent (AA)** ([`src/accounting_agent.py`](src/accounting_agent.py)): Reads `reports/transactions.json` delivered by BTA and generates the expandable **Balance** webpage ([`reports/balance.html`](reports/balance.html)) and [`reports/balance.json`](reports/balance.json) per **Bank** and **Bank Account / IBAN** with columns `#`, `Date`, `Description`, `Incoming`, `Expenses`, and `Source PDF`.
3. **Standalone or Combined Execution**:
   - When running together (`main.py` or `main.py --watch`), BTA is initialized with `extra_tools=[notify_accounting_agent]` so it notifies AA to recalculate the Balance whenever new PDFs are parsed.
   - Either agent can also be run standalone via `--bta-only` (BTA with `extra_tools=None`) or `--aa-only`.

---

## Project Layout

```text
lca-two-agents/
├── .env.example
├── pyproject.toml          # Links ../lca-single-agent & exports editable package `lca_two_agents`
├── main.py                 # CLI supporting BTA->AA, --watch (15m), --bta-only, --aa-only, --rerender
├── reports/
│   ├── transactions.json   # Delivered by BTA
│   ├── transactions.html   # Expandable BTA Transactions webpage
│   ├── balance.json        # Delivered by AA
│   └── balance.html        # Expandable AA Balance webpage
├── src/
│   ├── accounting_agent.py # build_accounting_agent() + notify_accounting_agent handoff tool
│   └── tools.py            # AA Balance schemas, tools, and expandable HTML renderer
└── tests/
    └── test_two_agents.py  # End-to-end tests for BTA -> AA and notify_accounting_agent
```

---

## CLI Usage

```bash
cd /Users/marcomaccio/Documents/development/personal/langchain-ecosystem/langchain/lca-two-agents

# 1. Run full Two-Agent Pipeline (BTA -> AA together):
uv run python main.py "/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"

# 2. Watch folder every 15 minutes (BTA parses new PDFs -> notifies AA to recalculate Balance):
uv run python main.py --watch "/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"

# 3. Run ONLY Agent 1 (BTA standalone without AA):
uv run python main.py --bta-only "/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"

# 4. Run ONLY Agent 2 (AA standalone on existing reports/transactions.json):
uv run python main.py --aa-only

# 5. Re-render both HTML pages from cached JSON (<0.1s, no LLM call):
uv run python main.py --rerender

# 6. Run unit tests & linter:
uv run pytest -v
uv run ruff check .
```
