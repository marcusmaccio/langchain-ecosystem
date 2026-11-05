# Local Multi-Agent Financial Ingestion, Reconciliation & Dispatch Pipeline

Implementation of the technical specification described in `docs/specs/transaction_ingestion_pipeline_specification.md`. Built with **LangGraph**, **LangChain**, and local LLM inference via **LM Studio** on Apple Silicon.

## Architecture

The pipeline processes financial statements sequentially across 5 specialized agent nodes:

1. **Reader & Normalizer Agent** (`reader_agent_node`): Extracts raw CSV/PDF content, verifies LM Studio connectivity, and parses transactions into normalized Pydantic schemas (`CleanTransaction`, `TransactionBatch`).
2. **Storage Agent** (`storage_agent_node`): Idempotently stores transactions into SQLite (`transactions` table).
3. **Reconciliation Agent** (`reconciliation_agent_node`): Matches transactions against `expected_invoices`, tagging records as `EXACT_MATCH`, `AMOUNT_MISMATCH`, or `UNMATCHED` and calculating variances.
4. **Variance Reporting Agent** (`reporting_agent_node`): Generates audit exception files in both CSV and formatted Excel (`.xlsx`) with auto-fitted columns.
5. **Dispatch Agent** (`dispatch_agent_node`): Evaluates discrepancy count and variance thresholds, sending alerts via Webhook or SMTP.

---

## Project Structure

```
├── agents/                     # Clean, single-file agent modules
│   ├── reader_agent.py         # Agent 1 (Reader & Normalizer)
│   ├── storage_agent.py        # Agent 2 (Database Storage)
│   ├── reconciliation_agent.py # Agent 3 (Reconciliation Engine)
│   ├── reporting_agent.py      # Agent 4 (Variance Reporting)
│   └── dispatch_agent.py       # Agent 5 (Automated Dispatch)
├── harness.py                  # Orchestration harness (LangGraph StateGraph)
├── run_core_pipeline.py        # Runner for 3-agent pipeline
├── run_full_pipeline.py        # Runner for 5-agent pipeline
├── run_dry_run.py              # Instant offline demo runner (<1s)
├── main.py                     # CLI entrypoint
├── docs/                       # Complete documentation guides
│   ├── README.md               # Master documentation index
│   ├── getting_started.md      # Setup, LM Studio, & installation
│   ├── architecture.md         # StateGraph & Agent architecture
│   ├── configuration.md        # Environment variables & options
│   ├── usage_guide.md          # Detailed operational guide
│   └── specs/                  # Original design specifications
├── tests/                      # Full pytest test suite (15 tests)
├── pyproject.toml
└── requirements.txt
```

---

## Setup & Execution

### 1. Requirements

- Python >= 3.11
- LM Studio running locally on `http://localhost:1234/v1` with a loaded model (e.g. `qwen3.8-27b-uncensored-mlx`).

### 2. Install Dependencies

Using `uv`:
```bash
uv venv --python 3.13 .venv
uv pip install -r requirements.txt
```

Or standard virtualenv:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run Tests

```bash
.venv/bin/pytest -v tests
```

## Documentation

Comprehensive documentation is available in the [`docs/`](docs/) directory:

- [**Documentation Index**](docs/README.md): Master navigation guide.
- [**Getting Started Guide**](docs/getting_started.md): Installation, LM Studio configuration, testing, and running.
- [**Architecture & Design**](docs/architecture.md): LangGraph StateGraph, shared `AgentState`, and agent node specs.
- [**Configuration Reference**](docs/configuration.md): Environment variables, thresholds, and webhook/SMTP configs.
- [**Operational Usage Guide**](docs/usage_guide.md): In-depth guide for statements (CSV/PDF), reports, and querying SQLite.
- [**Technical Specification**](docs/specs/transaction_ingestion_pipeline_specification.md): Original specification.

---

## Quick Start & Runner Files

Three dedicated runner scripts are provided for different use cases:

### 1. Core 3-Agent Pipeline (`run_core_pipeline.py`)
Runs the ingestion and reconciliation loop: **Reader** $\to$ **Storage** $\to$ **Reconciliation** (omits report generation and external alert dispatch).
```bash
.venv/bin/python run_core_pipeline.py
# Or with custom statement:
.venv/bin/python run_core_pipeline.py --file path/to/statement.csv
```

### 2. Full 5-Agent Pipeline (`run_full_pipeline.py`)
Runs all 5 agents: **Reader** $\to$ **Storage** $\to$ **Reconciliation** $\to$ **Reporting** $\to$ **Dispatch**.
```bash
.venv/bin/python run_full_pipeline.py
# Or specify dispatch channel:
.venv/bin/python run_full_pipeline.py --channel webhook
```

### 3. Instant Dry-Run / Offline Demo (`run_dry_run.py`)
Runs the entire 5-agent pipeline using deterministic sample data and mocked network/LLM responses. Useful for testing and demos in <1 second without waiting on local LLM inference.
```bash
.venv/bin/python run_dry_run.py
```

