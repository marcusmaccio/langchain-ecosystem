# LangGraph StateGraph Workflow — BTA $\rightarrow$ AA (`lca-langgraph-agents`)

> **Full Conceptual & Architectural Documentation**:
> - [Stage 3 Learning Guide (`docs/langgraph/lca-langgraph-agents/README.md`)](../../docs/langgraph/lca-langgraph-agents/README.md)
> - [Stage 3 Architecture Deep Dive (`docs/langgraph/lca-langgraph-agents/architecture.md`)](../../docs/langgraph/lca-langgraph-agents/architecture.md)

## Project Details

`lca-langgraph-agents` coordinates **Agent 1 (Bank Transaction Agent / BTA)** and **Agent 2 (Accounting Agent / AA)** using a declarative **LangGraph v1.x `StateGraph`** while reusing 100% of both agents from [`../../langchain/lca-single-agent`](../../langchain/lca-single-agent) and [`../../langchain/lca-two-agents`](../../langchain/lca-two-agents).

- **Graph Nodes**:
  1. `discover_files`: Deterministic gatekeeper node that inspects the PDF folder against `reports/transactions.json`.
  2. `bta_node`: Runs **BTA** (`build_bta_agent()` in pure standalone mode) to extract transactions and update `reports/transactions.json` + `reports/transactions.html`.
  3. `aa_node`: Runs **AA** (`build_accounting_agent()`) to compute the Balance per Bank and Bank Account and generate `reports/balance.json` + `reports/balance.html`.
- **Conditional Edges**:
  - `route_after_discovery`: Transitions to `bta_node` when PDFs need processing, or short-circuits directly to `END` when no new PDFs are found during the 15-minute `--watch` cycle.
  - `route_after_bta`: Transitions to `aa_node` once `reports/transactions.json` is ready.

---

## Project Layout

```text
lca-langgraph-agents/
├── .env.example
├── pyproject.toml          # Links ../../langchain/lca-single-agent & ../../langchain/lca-two-agents
├── main.py                 # CLI runner for full workflow, --watch (15m), --graph, and --rerender
├── reports/
│   ├── transactions.json
│   ├── transactions.html
│   ├── balance.json
│   └── balance.html
├── src/
│   └── workflow.py         # WorkflowState, nodes, conditional routers, and build_bta_aa_graph()
└── tests/
    └── test_workflow.py    # Unit tests for full traversal, incremental short-circuit, and Mermaid export
```

---

## CLI Usage

```bash
cd /Users/marcomaccio/Documents/development/personal/langchain-ecosystem/langgraph/lca-langgraph-agents

# 1. Print the compiled LangGraph Mermaid state machine diagram:
uv run python main.py --graph

# 2. Run the full LangGraph workflow (discover_files -> bta_node -> aa_node):
uv run python main.py "/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"

# 3. Run the 15-minute incremental watcher via the LangGraph StateGraph:
uv run python main.py --watch "/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"

# 4. Re-render both HTML pages from cached JSON (<0.1s, no LLM call):
uv run python main.py --rerender

# 5. Run unit tests & linter:
uv run pytest -v
uv run ruff check .
```
