# Getting Started Guide

This guide walks you through setting up your environment, running the local LM Studio model, executing tests, and running the financial ingestion & reconciliation agents.

---

## 1. Prerequisites

- **macOS** on Apple Silicon (M1/M2/M3/M4) recommended for local Metal GPU acceleration.
- **Python 3.11+** installed (Python 3.13 tested).
- **[LM Studio](https://lmstudio.ai/)** (or compatible local OpenAI-compatible inference server).
- **`uv`** (recommended) or standard `python3 -m venv`.

---

## 2. Setting Up the Local LLM (LM Studio)

The pipeline's **Reader & Normalizer Agent** uses a local LLM to parse unstructured statements into structured JSON.

1. **Download & Open LM Studio**:
   - Start the LM Studio application.
2. **Download Model**:
   - Recommended: `qwen3.8-27b-uncensored-mlx` or `Qwen2.5-Coder-32B-Instruct-GGUF`.
   - Any capable instruction-following model with JSON output capabilities will work.
3. **Start the Local Server**:
   - Go to the **Developer / Local Server** tab (`<->` icon).
   - Select your model and click **Load Model**.
   - Ensure the server is listening on port `1234` (`http://localhost:1234/v1`).
   - Turn **CORS ON** (default).

> [!TIP]
> You can quickly verify LM Studio is running from your terminal:
> ```bash
> curl -s http://localhost:1234/v1/models
> ```

---

## 3. Environment & Dependency Installation

Clone or open the repository root:

```bash
cd /Users/marcomaccio/Documents/development/personal/langchain/deep-agents-example
```

### Option A: Using `uv` (Recommended - fast)

```bash
# Create virtualenv with Python 3.13 or 3.11+
uv venv --python 3.13 .venv

# Install all dependencies and development tools
uv pip install -r requirements.txt
```

### Option B: Using standard Python `venv` + `pip`

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

---

## 4. Running the Test Suite

Verify that all schemas, tools, agent nodes, and the LangGraph harness are working properly:

```bash
.venv/bin/pytest -v tests
```

Expected output:
```
tests/test_agents.py::test_reader_agent_unsupported_format PASSED
tests/test_agents.py::test_storage_agent_node PASSED
tests/test_agents.py::test_reconciliation_agent_node PASSED
tests/test_agents.py::test_reporting_agent_node PASSED
tests/test_agents.py::test_dispatch_agent_node_webhook PASSED
tests/test_agents.py::test_agent_classes_direct_instantiation PASSED
tests/test_db.py::test_init_database PASSED
tests/test_harness.py::test_build_financial_pipeline_structure PASSED
tests/test_harness.py::test_full_pipeline_flow PASSED
tests/test_schemas.py::test_clean_transaction_valid PASSED
tests/test_schemas.py::test_transaction_batch PASSED
tests/test_schemas.py::test_reconciliation_record PASSED
tests/test_tools.py::test_read_raw_csv_content PASSED
tests/test_tools.py::test_read_csv_not_found PASSED
tests/test_tools.py::test_extract_pdf_not_found PASSED
============================== 15 passed in 1.00s ==============================
```

---

## 5. Running the Pipeline

Three dedicated runner scripts are available based on your workflow needs:

| Script | Purpose | Needs LM Studio? |
|---|---|:---:|
| `run_dry_run.py` | Instant offline demo (<1s) using realistic sample data | No |
| `run_core_pipeline.py` | Core 3-agent pipeline (Reader $\to$ Storage $\to$ Reconciliation) | Yes |
| `run_full_pipeline.py` | Full 5-agent pipeline (Ingestion $\to$ DB $\to$ Recon $\to$ Reports $\to$ Dispatch) | Yes |

### 5.1 Quick Dry-Run (No local LLM needed)

```bash
.venv/bin/python run_dry_run.py
```
This runs all 5 agents deterministically, initializes SQLite, checks reconciliation against expected rent & utility invoices, outputs styled Excel & CSV reports in `reports/`, and dispatches a test alert.

### 5.2 Core 3-Agent Pipeline

```bash
.venv/bin/python run_core_pipeline.py
```
Or process a custom statement:
```bash
.venv/bin/python run_core_pipeline.py --file path/to/my_statement.csv
```

### 5.3 Full 5-Agent Pipeline

```bash
.venv/bin/python run_full_pipeline.py
```
Or process a custom statement and specify the dispatch channel:
```bash
.venv/bin/python run_full_pipeline.py --file path/to/my_statement.pdf --channel webhook
```

---

## 6. Inspecting the Ingested Data

Transactions are saved into the SQLite database (`bank_reconciliation.db`):

```bash
sqlite3 bank_reconciliation.db "SELECT * FROM transactions;"
```

And expected invoices:
```bash
sqlite3 bank_reconciliation.db "SELECT * FROM expected_invoices;"
```

