# Stage 1 Learning Guide — Single Agent in Pure LangChain (`lca-single-agent`)

- **Project Folder**: [`../../../langchain/lca-single-agent/`](../../../langchain/lca-single-agent/)
- **Architecture Deep Dive**: [`architecture.md`](architecture.md)

---

## 1. What Is a Pure LangChain Agent?

A LangChain v1.x agent (`langchain.agents.create_agent`) combines three foundational pieces:
1. **A Chat Model (`init_chat_model`)**: The reasoning engine — here, `qwen3.8-27b-uncensored-mlx` running locally on Apple Silicon via **LM Studio** (`http://localhost:1234/v1`).
2. **A Set of Tools (`@tool`)**: Python functions decorated with `@tool` and typed with **Pydantic schemas** (`TransactionItem`) so the LLM knows *when* and *how* to call them with validated structured arguments.
3. **A System Prompt**: Clear, sequential instructions guiding the agent's ReAct (Reason + Act) loop.

---

## 2. Dividing Responsibilities: LLM Reasoning vs. Deterministic Tools

A crucial lesson from Stage 1 is **never asking the LLM to recompute what deterministic Python code can guarantee with 100% accuracy**:

| Task | Handled By | Why? |
| :--- | :--- | :--- |
| Parsing unstructured statement lines into transactions | **LLM (`qwen3.8-27b-uncensored-mlx`)** | Bank statement layouts vary across lines; the LLM excels at semantic extraction into `TransactionItem`. |
| Detecting Bank Name & Bank Account / IBAN | **Deterministic Header Parser + LLM** | `_extract_bank_and_account` deterministically inspects the PDF header (`Banque Migros SA`, `CH76 ...`) and injects it into the extracted header so every transaction carries exact account metadata. |
| Counting files, deduplicating transactions, summing credits/debits | **Deterministic Python Tool (`generate_transactions_webpage`)** | Guarantees zero rounding errors, exact date boundaries (`start_date`, `end_date`), and deterministic composite deduplication keys (`date`, `amount`, `currency`, `description`, `reference`). |
| Changing HTML layout / UI styling | **Cached JSON (`--rerender`)** | Persisting `reports/transactions.json` lets us re-render `reports/transactions.html` in `<0.1s` without re-invoking the LLM. |

---

## 3. Standalone by Default (`extra_tools=None`), Ready for Composition

In [`src/agent.py`](../../../langchain/lca-single-agent/src/agent.py), `build_single_agent(model_name, base_url, extra_tools=None)` is designed so that:
- **Standalone Mode (`extra_tools=None`)**: BTA loads only its 3 core tools (`list_pdf_files`, `read_bank_statement_pdf`, `generate_transactions_webpage`). It has **zero awareness** of any downstream agent and serves as a pure single-agent reference.
- **Extensible Mode (`extra_tools=[...]`)**: When imported as an editable package (`lca_single_agent`) by Stage 2 (`lca-two-agents`), additional handoff tools can be attached without modifying or duplicating BTA's source code.
