# Project Documentation Index

Welcome to the documentation for the **Local Multi-Agent Financial Ingestion, Reconciliation & Dispatch Pipeline**.

---

## Documentation Roadmap

| Document | Description |
|---|---|
| [**Getting Started Guide**](file:///Users/marcomaccio/Documents/development/personal/langchain/deep-agents-example/docs/getting_started.md) | Setup instructions, LM Studio configuration, virtual environment, running tests, and executing the pipeline. |
| [**Architecture & Design**](file:///Users/marcomaccio/Documents/development/personal/langchain/deep-agents-example/docs/architecture.md) | StateGraph topology, `AgentState` schema, 5-agent node breakdown, database design, and local LLM resiliency. |
| [**Configuration Reference**](file:///Users/marcomaccio/Documents/development/personal/langchain/deep-agents-example/docs/configuration.md) | Complete reference of environment variables, LM Studio engine options, SMTP and Webhook dispatch configs. |
| [**Operational Usage Guide**](file:///Users/marcomaccio/Documents/development/personal/langchain/deep-agents-example/docs/usage_guide.md) | Step-by-step usage guide for all 3 execution modes, input statement formats (CSV & PDF), and troubleshooting. |
| [**Original Technical Specification**](file:///Users/marcomaccio/Documents/development/personal/langchain/deep-agents-example/docs/specs/transaction_ingestion_pipeline_specification.md) | Original design specification detailing target data contracts, ledger models, and topologies. |

---

## Quick Command Reference

```bash
# 1. Run unit tests (15 passing)
.venv/bin/pytest -v tests

# 2. Instant offline dry-run (< 1 second)
.venv/bin/python run_dry_run.py

# 3. Core 3-agent pipeline (Reader -> Storage -> Reconciliation)
.venv/bin/python run_core_pipeline.py

# 4. Full 5-agent pipeline with reporting and alerts
.venv/bin/python run_full_pipeline.py
```

