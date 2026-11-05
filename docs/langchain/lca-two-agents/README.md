# Stage 2 Learning Guide — Two Agents in Pure LangChain (`lca-two-agents`)

- **Project Folder**: [`../../../langchain/lca-two-agents/`](../../../langchain/lca-two-agents/)
- **Architecture Deep Dive**: [`architecture.md`](architecture.md)

---

## 1. Zero-Duplication Agent Reuse via Editable Packages

When building a second project (`lca-two-agents`) that needs the **Bank Transaction Agent (BTA)** from `lca-single-agent`, copying files creates maintenance drift. Instead:
1. `lca-single-agent` exposes its `src/` folder as the installable package `lca_single_agent`.
2. `lca-two-agents/pyproject.toml` links it as a local editable `uv` source:
   ```toml
   [tool.uv.sources]
   lca-single-agent = { path = "../lca-single-agent", editable = true }
   ```
Any enhancement to BTA in `lca-single-agent` immediately takes effect in `lca-two-agents` with **zero duplicated code**.

---

## 2. How Two Agents Communicate in Pure LangChain (`notify_accounting_agent`)

In pure LangChain (before introducing LangGraph), how can Agent 1 (BTA) trigger Agent 2 (**Accounting Agent / AA**) when it finishes parsing a new PDF statement?

We use the **Agent-to-Agent Handoff Tool Pattern**:
- In [`src/accounting_agent.py`](../../../langchain/lca-two-agents/src/accounting_agent.py), we define `@tool def notify_accounting_agent(...)`, which instantiates and invokes the **Accounting Agent (AA)** on `reports/transactions.json`.
- When running both agents together, `lca-two-agents/main.py` initializes BTA with:
  ```python
  bta_agent = build_bta_agent(extra_tools=[notify_accounting_agent])
  ```
- When BTA finishes updating `reports/transactions.json` (either in one-shot mode or upon discovering a new PDF during the 15-minute `--watch` cycle), it invokes `notify_accounting_agent` to trigger AA to recalculate `reports/balance.html` and `reports/balance.json`.

---

## 3. Keeping Standalone Execution Intact (`--bta-only` & `--aa-only`)

Crucially, adding Agent 2 never prevents running either agent standalone:

| Execution Mode | How BTA Is Initialized | Active Tools on BTA | Behavior |
| :--- | :--- | :--- | :--- |
| **Standalone BTA** (`lca-single-agent` or `lca-two-agents --bta-only`) | `build_single_agent()` (`extra_tools=None`) | `list_pdf_files`, `read_bank_statement_pdf`, `generate_transactions_webpage` | Runs purely as a single agent. Produces `transactions.json` and `transactions.html` with **no dependency on or awareness of** the Accounting Agent. |
| **Two-Agent Pipeline (BTA $\rightarrow$ AA)** (`lca-two-agents`) | `build_single_agent(extra_tools=[notify_accounting_agent])` | Core BTA tools **+** `notify_accounting_agent` | When BTA finishes parsing PDFs (or discovers a new PDF during the 15-minute `--watch` cycle), BTA calls `notify_accounting_agent` to message AA and trigger a recalculation of `balance.html` and `balance.json`. |
| **Standalone AA** (`lca-two-agents --aa-only`) | `build_accounting_agent()` | `read_bta_transactions_json`, `generate_balance_webpage` | Runs only Agent 2 (Accounting Agent) on an existing `reports/transactions.json`. |
