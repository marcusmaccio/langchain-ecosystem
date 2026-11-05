# Stage 3 Learning Guide — Multi-Agent Orchestration with LangGraph (`lca-langgraph-agents`)

- **Project Folder**: [`../../../langgraph/lca-langgraph-agents/`](../../../langgraph/lca-langgraph-agents/)
- **Architecture Deep Dive**: [`architecture.md`](architecture.md)

---

## 1. Why LangGraph? (Evolution from Stage 1 $\rightarrow$ Stage 2 $\rightarrow$ Stage 3)

| Stage | Project | How Agents Are Built & Coordinated | Key Architectural Lesson |
| :--- | :--- | :--- | :--- |
| **Stage 1** | [`lca-single-agent`](../lca-single-agent/README.md) | **Single Agent (`BTA`)**: `create_agent` + 3 tools (`list_pdf_files`, `read_bank_statement_pdf`, `generate_transactions_webpage`) | Separate LLM extraction from deterministic Python calculations (deduplication, counters, JSON caching). |
| **Stage 2** | [`lca-two-agents`](../lca-two-agents/README.md) | **Two Agents in Pure LangChain (`BTA` + `AA`)**: BTA is given a handoff tool (`notify_accounting_agent`) to call AA when new files are parsed. | Reuse agents via editable packages (`editable = true`). Works well for 2 agents, but mixes *routing logic* into BTA's toolset. |
| **Stage 3** | **[`lca-langgraph-agents`](.)** | **Declarative `StateGraph` (`discover_files` $\rightarrow$ `bta_node` $\rightarrow$ `aa_node`)**: LangGraph owns the state and routing edges; BTA and AA run as pure, decoupled nodes. | **Separation of Concerns**: Agents focus 100% on their domain task; **LangGraph** manages state transitions, conditional branching, and execution traces. |

---

## 2. The 4 Pillars of LangGraph (`StateGraph`)

### Pillar A — Typed Shared State (`WorkflowState`) & Reducers
In LangGraph, every node reads from and writes partial updates to a strongly-typed state dictionary (`WorkflowState`):
- Standard keys (`should_process`, `new_files`, `bta_response`, `aa_response`) are replaced when a node returns an update.
- **Reducer keys** (`workflow_steps: Annotated[list[str], operator.add]`) **append** items automatically across nodes, producing a clean execution audit trail.

### Pillar B — Graph Nodes (`builder.add_node`)
Each node is a clean function `node(state: WorkflowState) -> WorkflowState`:
1. **`discover_files_node` (`discover_files`)**: Deterministic gatekeeper (zero LLM cost) that checks the folder against `reports/transactions.json` and sets `should_process = True/False`.
2. **`bta_node`**: Runs **Agent 1 (BTA)** (`build_bta_agent()` with `extra_tools=None`). Because LangGraph owns the transition to AA, BTA runs in its pure standalone configuration!
3. **`aa_node`**: Runs **Agent 2 (Accounting Agent)** (`build_accounting_agent()`) to generate `reports/balance.html` and `reports/balance.json`.

### Pillar C — Conditional Edges (`builder.add_conditional_edges`)
- **`route_after_discovery(state)`**: Routes to `bta_node` when `should_process == True`, or short-circuits directly to `END` (`__end__`) when `should_process == False` (e.g., during a 15-minute `--watch` check when no new PDFs arrived).
- **`route_after_bta(state)`**: Routes to `aa_node` once `reports/transactions.json` is ready.

### Pillar D — Compilation & Introspection (`builder.compile()`)
- `builder.compile()` validates the state machine and exposes `graph.invoke(initial_state)` as well as `graph.get_graph().draw_mermaid()` (`uv run python main.py --graph`).
