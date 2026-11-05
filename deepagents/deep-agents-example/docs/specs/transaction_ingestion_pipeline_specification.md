# Technical Specification: Local Multi-Agent Financial Ingestion, Reconciliation & Dispatch Pipeline

## 1. System Overview & Architecture

This document specifies the technical design, data contracts, and implementation for an offline, multi-agent financial transaction processing pipeline built on **LangChain / LangGraph** and powered locally on Apple Silicon using **LM Studio** (model: `qwen3.8-27b-uncensored-mlx` or compatible GGUF/MLX engines).

The pipeline ingests raw, unstructured financial statements (CSV, PDF), extracts and validates transaction records, persists them to a relational database, reconciles them against expected accounts receivable/payable, generates variance audit reports, and triggers automated alerts when discrepancy thresholds are breached.

### High-Level Topology

```
[START]
   │
   ▼
┌──────────────────────────────────────────────┐
│ Agent 1: Reader & Normalizer Node (Local LLM) │
│ - Delimiter sniffing / PDF extraction        │
│ - LM Studio resilient health check & parsing  │
│ - Strict Pydantic JSON schema compliance     │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ Agent 2: Database Storage Node (SQLite)      │
│ - Schema initialization                      │
│ - Idempotent upsert (INSERT OR REPLACE)      │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ Agent 3: Reconciliation Node                 │
│ - Cross-reference vs `expected_invoices`     │
│ - Status tagging (EXACT, MISMATCH, UNMATCHED)│
│ - Variance calculation                       │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ Agent 4: Variance Reporting Node             │
│ - Filter exception records                   │
│ - Generate CSV & styled Excel (.xlsx) files  │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ Agent 5: Automated Dispatch Node             │
│ - Threshold evaluation (count, abs variance) │
│ - Multi-channel alert (SMTP / Webhook)       │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
                     [END]
```

---

## 2. Shared State & Data Contracts

All agents communicate state transitions over a typed state graph using Pydantic data schemas.

### 2.1 State Graph Schema (`AgentState`)

```python
from typing import Annotated, List, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    raw_file_path: str
    transactions: List[dict]
    reconciliation_results: List[dict]
    db_status: str
    report_path: Optional[str]
    dispatch_status: str  # PENDING, SENT_SMTP, SENT_WEBHOOK, SKIPPED_THRESHOLD, FAILED
    messages: Annotated[List[BaseMessage], add_messages]
```

### 2.2 Domain Entities

```python
from typing import List, Optional
from pydantic import BaseModel, Field

class CleanTransaction(BaseModel):
    transaction_id: str = Field(description="Unique reference, line hash, or clean ID")
    date: str = Field(description="ISO 8601 date format YYYY-MM-DD")
    description: str = Field(description="Normalized narrative, payee, or transaction description")
    amount: float = Field(description="Signed numeric amount (debits negative, credits positive)")
    currency: str = Field(default="CHF", description="3-letter ISO currency code (e.g., CHF, EUR, USD)")

class TransactionBatch(BaseModel):
    items: List[CleanTransaction]

class ReconciliationRecord(BaseModel):
    transaction_id: str
    expected_id: Optional[str] = None
    status: str  # EXACT_MATCH, AMOUNT_MISMATCH, UNMATCHED
    variance: float = 0.0
    notes: str
```

---

## 3. Storage & Ledger Schema (SQLite)

The system maintains two core relational tables:

```sql
-- Ingested actual transactions
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Expected invoices / rent roll commitments
CREATE TABLE IF NOT EXISTS expected_invoices (
    expected_id TEXT PRIMARY KEY,
    party_name TEXT NOT NULL,
    expected_amount REAL NOT NULL,
    due_date TEXT NOT NULL,
    currency TEXT NOT NULL
);
```

---

## 4. Local Offline Inference Engine (LM Studio Configuration)

### 4.1 LM Studio Server Settings
* **Model:** `qwen3.8-27b-uncensored-mlx` (or `Qwen2.5-Coder-32B-Instruct-GGUF`)
* **Endpoint:** `http://localhost:1234/v1` (with fallback to LAN IP e.g. `http://192.168.1.21:1234/v1`)
* **Context Length ($n_{\text{ctx}}$):** $\ge 16384$ tokens
* **GPU Offload:** 100% Metal layers on Apple Silicon Unified Memory
* **Sampling parameters:** `temperature=0.1`, `top_p=0.85`
* **JSON Grammar Enforcement:** `{"response_format": {"type": "json_object"}}`

### 4.2 Resilient Connection & Health Check Logic

Before dispatching prompts, the agent pings the `/v1/models` route to avoid hung execution threads if the local daemon is down or unreachable.

---

## 5. End-to-End Implementation Code

The complete standalone runnable pipeline is provided below:

```python
"""
Local Multi-Agent Financial Ingestion, Reconciliation, and Dispatch Pipeline
Compatible with LM Studio on Apple Silicon.
"""

import csv
import json
import os
import smtplib
import sqlite3
from datetime import datetime
from email.message import EmailMessage
from typing import Annotated, Any, Dict, List, Optional, TypedDict

import pandas as pd
import requests
from pydantic import BaseModel, Field, ValidationError
from pypdf import PdfReader

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


# ==============================================================================
# 1. DOMAIN SCHEMAS & STATE
# ==============================================================================

class CleanTransaction(BaseModel):
    transaction_id: str = Field(description="Unique reference, line hash, or clean ID")
    date: str = Field(description="ISO 8601 date format YYYY-MM-DD")
    description: str = Field(description="Normalized narrative, payee, or transaction description")
    amount: float = Field(description="Signed numeric amount (debits negative, credits positive)")
    currency: str = Field(default="CHF", description="3-letter ISO currency code")


class TransactionBatch(BaseModel):
    items: List[CleanTransaction]


class ReconciliationRecord(BaseModel):
    transaction_id: str
    expected_id: Optional[str] = None
    status: str  # EXACT_MATCH, AMOUNT_MISMATCH, UNMATCHED
    variance: float = 0.0
    notes: str


class AgentState(TypedDict):
    raw_file_path: str
    transactions: List[dict]
    reconciliation_results: List[dict]
    db_status: str
    report_path: Optional[str]
    dispatch_status: str
    messages: Annotated[List[BaseMessage], add_messages]


# ==============================================================================
# 2. LOCAL ENGINE HEALTH & CONNECTION HANDLER
# ==============================================================================

def check_lm_studio_health(base_url: str, timeout: float = 3.0) -> bool:
    """Verifies that the local LM Studio daemon is active and responsive."""
    health_endpoint = f"{base_url.rstrip('/')}/models"
    try:
        response = requests.get(health_endpoint, timeout=timeout)
        if response.status_code == 200:
            models_data = response.json().get("data", [])
            loaded_ids = [m.get("id") for m in models_data]
            print(f"[OK] LM Studio active at {base_url}. Loaded: {loaded_ids}")
            return True
        return False
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return False


def get_resilient_lm_studio_client(
    primary_url: str = "http://localhost:1234/v1",
    fallback_url: str = "http://192.168.1.21:1234/v1",
    model_name: str = "qwen3.8-27b-uncensored-mlx"
) -> ChatOpenAI:
    """Connects to primary localhost endpoint or falls back to LAN IP."""
    target_url = primary_url
    if not check_lm_studio_health(target_url):
        print(f"[WARN] Failed connecting to {primary_url}. Testing fallback: {fallback_url}")
        if check_lm_studio_health(fallback_url):
            target_url = fallback_url
        else:
            raise ConnectionError(
                f"LM Studio offline at both {primary_url} and {fallback_url}. "
                "Ensure LM Studio Local Server is started with CORS enabled."
            )

    return ChatOpenAI(
        base_url=target_url,
        api_key="not-needed",
        model=model_name,
        temperature=0.1,
        request_timeout=60.0,
        max_retries=2,
        model_kwargs={"response_format": {"type": "json_object"}}
    )


# ==============================================================================
# 3. EXTRACTION TOOLS & DATABASE INITIALIZATION
# ==============================================================================

DB_PATH = "bank_reconciliation.db"


def init_database():
    """Initializes tables and seeds test expectations."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expected_invoices (
                expected_id TEXT PRIMARY KEY,
                party_name TEXT NOT NULL,
                expected_amount REAL NOT NULL,
                due_date TEXT NOT NULL,
                currency TEXT NOT NULL
            );
        """)
        cursor.execute("SELECT COUNT(*) FROM expected_invoices;")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("""
                INSERT INTO expected_invoices (expected_id, party_name, expected_amount, due_date, currency)
                VALUES (?, ?, ?, ?, ?);
            """, [
                ("EXP-RENT-001", "LOYER APPARTEMENT DUPLEX", 2150.00, "2026-10-31", "CHF"),
                ("EXP-UTIL-002", "SUNRISE COMMUNICATIONS", -89.90, "2026-10-30", "CHF"),
                ("EXP-POW-003", "SERVICES INDUSTRIELS DE GENEVE", -150.00, "2026-11-05", "CHF")
            ])
        conn.commit()


@tool
def read_raw_csv_content(file_path: str) -> str:
    """Reads raw CSV content with delimiter autodetection."""
    if not os.path.exists(file_path):
        return f"Error: File {file_path} not found."
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ";" if ";" in sample else ","
        reader = csv.reader(f, delimiter=delimiter)
        rows = [f"ROW {idx}: {row}" for idx, row in enumerate(reader) if any(row)]
        return "\n".join(rows[:120])


@tool
def extract_pdf_bank_statement(file_path: str) -> str:
    """Extracts text stream from PDF statement pages."""
    if not os.path.exists(file_path):
        return f"Error: File {file_path} not found."
    try:
        reader = PdfReader(file_path)
        extracted = []
        for i, page in enumerate(reader.pages[:5]):
            text = page.extract_text()
            if text:
                extracted.append(f"--- PAGE {i+1} ---\n{text.strip()}")
        return "\n".join(extracted)
    except Exception as e:
        return f"PDF Extraction Error: {str(e)}"


# ==============================================================================
# 4. PIPELINE AGENT NODES
# ==============================================================================

def reader_agent_node(state: AgentState) -> dict:
    """Node 1: Parses raw statement into normalized JSON using local Qwen."""
    file_path = state["raw_file_path"]
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        raw_text = read_raw_csv_content.invoke({"file_path": file_path})
    elif ext == ".pdf":
        raw_text = extract_pdf_bank_statement.invoke({"file_path": file_path})
    else:
        return {
            "transactions": [],
            "messages": [HumanMessage(content=f"ReaderAgent: Unsupported format {ext}")]
        }

    try:
        llm = get_resilient_lm_studio_client()
    except ConnectionError as err:
        return {
            "transactions": [],
            "messages": [HumanMessage(content=f"ReaderAgent ABORT: {str(err)}")]
        }

    schema_def = json.dumps(TransactionBatch.model_json_schema(), indent=2)
    system_prompt = (
        "You are an offline bank statement ingestion agent.\n"
        "Output ONLY a raw JSON object strictly adhering to this JSON Schema:\n"
        f"{schema_def}\n\n"
        "Rules:\n"
        "1. Dates must strictly follow YYYY-MM-DD.\n"
        "2. Parse amounts as signed floats (debits negative, credits positive).\n"
        "3. Strip internal transaction noise from descriptions.\n"
        "4. Default currency to CHF if not specified."
    )

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Raw Bank Statement:\n\n{raw_text}")
        ])
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        batch = TransactionBatch.model_validate(json.loads(content))
        records = [item.model_dump() for item in batch.items]
        msg = f"ReaderAgent: Successfully parsed {len(records)} transactions via local LLM."
    except Exception as e:
        records = []
        msg = f"ReaderAgent Parsing Error: {str(e)}"

    return {"transactions": records, "messages": [HumanMessage(content=msg)]}


def storage_agent_node(state: AgentState) -> dict:
    """Node 2: Persists clean transactions into SQLite."""
    txs = state.get("transactions", [])
    if not txs:
        return {
            "db_status": "SKIPPED",
            "messages": [HumanMessage(content="StorageAgent: No records received.")]
        }

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR REPLACE INTO transactions (transaction_id, date, description, amount, currency)
            VALUES (:transaction_id, :date, :description, :amount, :currency);
        """, txs)
        conn.commit()

    return {
        "db_status": "COMMITTED",
        "messages": [HumanMessage(content=f"StorageAgent: Stored {len(txs)} transactions in {DB_PATH}.")]
    }


def reconciliation_agent_node(state: AgentState) -> dict:
    """Node 3: Matches actual transactions against expected ledger records."""
    txs = state.get("transactions", [])
    if not txs:
        return {
            "reconciliation_results": [],
            "messages": [HumanMessage(content="ReconciliationAgent: No records to reconcile.")]
        }

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT expected_id, party_name, expected_amount, currency FROM expected_invoices;")
        expected_records = cursor.fetchall()

    recon_results: List[dict] = []

    for tx in txs:
        tx_desc = tx["description"].upper()
        tx_amt = tx["amount"]
        matched = False

        for exp_id, party, exp_amt, exp_curr in expected_records:
            keywords = [w for w in party.upper().split() if len(w) > 3]
            if any(kw in tx_desc for kw in keywords):
                variance = round(tx_amt - exp_amt, 2)
                status = "EXACT_MATCH" if abs(variance) < 0.01 else "AMOUNT_MISMATCH"
                notes = (
                    f"Exact match with {exp_id} ({party})"
                    if status == "EXACT_MATCH"
                    else f"Partial match with {exp_id}. Variance: {variance} {tx.get('currency', 'CHF')}"
                )
                recon_results.append(ReconciliationRecord(
                    transaction_id=tx["transaction_id"],
                    expected_id=exp_id,
                    status=status,
                    variance=variance,
                    notes=notes
                ).model_dump())
                matched = True
                break

        if not matched:
            recon_results.append(ReconciliationRecord(
                transaction_id=tx["transaction_id"],
                expected_id=None,
                status="UNMATCHED",
                variance=0.0,
                notes="No matching expected invoice found in ledger"
            ).model_dump())

    exact_c = sum(1 for r in recon_results if r["status"] == "EXACT_MATCH")
    mismatch_c = sum(1 for r in recon_results if r["status"] == "AMOUNT_MISMATCH")
    unmatched_c = sum(1 for r in recon_results if r["status"] == "UNMATCHED")

    summary = f"ReconciliationAgent: Processed {len(recon_results)} items. Exact: {exact_c}, Mismatch: {mismatch_c}, Unmatched: {unmatched_c}."
    return {"reconciliation_results": recon_results, "messages": [HumanMessage(content=summary)]}


def reporting_agent_node(state: AgentState) -> dict:
    """Node 4: Produces CSV and formatted Excel reports for all variance items."""
    recon = state.get("reconciliation_results", [])
    tx_map = {t["transaction_id"]: t for t in state.get("transactions", [])}

    discrepancies = [r for r in recon if r["status"] in ("AMOUNT_MISMATCH", "UNMATCHED")]
    if not discrepancies:
        return {
            "report_path": None,
            "messages": [HumanMessage(content="ReportingAgent: Zero discrepancies. No report required.")]
        }

    report_rows = []
    for item in discrepancies:
        t_id = item["transaction_id"]
        tx_info = tx_map.get(t_id, {})
        report_rows.append({
            "Transaction ID": t_id,
            "Status": item["status"],
            "Booking Date": tx_info.get("date", "N/A"),
            "Description": tx_info.get("description", "N/A"),
            "Actual Amount": tx_info.get("amount", 0.0),
            "Expected ID": item.get("expected_id") or "UNASSIGNED",
            "Variance": item.get("variance", 0.0),
            "Currency": tx_info.get("currency", "CHF"),
            "Audit Notes": item.get("notes", "")
        })

    df = pd.DataFrame(report_rows)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("reports", exist_ok=True)
    csv_path = f"reports/variance_summary_{timestamp}.csv"
    xlsx_path = f"reports/variance_summary_{timestamp}.xlsx"

    df.to_csv(csv_path, index=False, sep=";", encoding="utf-8-sig")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Variances", index=False)
        worksheet = writer.sheets["Variances"]
        for col in worksheet.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            worksheet.column_dimensions[col[0].column_letter].width = max(max_len + 3, 12)

    msg = f"ReportingAgent: Exported exception files:\n  - CSV: {csv_path}\n  - Excel: {xlsx_path}"
    return {"report_path": xlsx_path, "messages": [HumanMessage(content=msg)]}


def dispatch_agent_node(state: AgentState) -> dict:
    """Node 5: Evaluates thresholds and triggers SMTP or Webhook dispatch."""
    report_path = state.get("report_path")
    reconciliation_results = state.get("reconciliation_results", [])

    COUNT_THRESHOLD = int(os.getenv("DISPATCH_COUNT_THRESHOLD", "1"))
    VARIANCE_SUM_THRESHOLD = float(os.getenv("DISPATCH_VARIANCE_THRESHOLD", "50.00"))
    DISPATCH_CHANNEL = os.getenv("DISPATCH_CHANNEL", "webhook").lower()
    WEBHOOK_URL = os.getenv("DISPATCH_WEBHOOK_URL", "https://httpbin.org/post")

    discrepancies = [r for r in reconciliation_results if r["status"] in ("AMOUNT_MISMATCH", "UNMATCHED")]
    total_abs_variance = sum(abs(r.get("variance", 0.0)) for r in discrepancies)
    discrepancy_count = len(discrepancies)

    breaches_count = discrepancy_count >= COUNT_THRESHOLD
    breaches_amount = total_abs_variance >= VARIANCE_SUM_THRESHOLD

    if not report_path or not (breaches_count or breaches_amount):
        msg = (
            f"DispatchAgent: Threshold not reached (Count: {discrepancy_count} < {COUNT_THRESHOLD}, "
            f"Variance: {total_abs_variance:.2f} < {VARIANCE_SUM_THRESHOLD:.2f}). Notification omitted."
        )
        return {"dispatch_status": "SKIPPED_THRESHOLD", "messages": [HumanMessage(content=msg)]}

    subject = f"[Action Required] Bank Reconciliation Variance Alert ({discrepancy_count} discrepancies)"
    body_text = (
        f"Reconciliation exception summary:\n"
        f"- Discrepancies Count: {discrepancy_count}\n"
        f"- Cumulative Absolute Variance: {total_abs_variance:.2f} CHF\n"
        f"- Report File: {os.path.basename(report_path)}"
    )

    try:
        if DISPATCH_CHANNEL == "smtp":
            smtp_user = os.getenv("SMTP_USER", "")
            smtp_pass = os.getenv("SMTP_PASS", "")
            to_email = os.getenv("ALERT_TO_EMAIL", "accounting@example.com")
            
            if not smtp_user or not smtp_pass:
                raise ValueError("SMTP credentials missing.")

            email_msg = EmailMessage()
            email_msg["Subject"] = subject
            email_msg["From"] = smtp_user
            email_msg["To"] = to_email
            email_msg.set_content(body_text)

            with open(report_path, "rb") as f:
                email_msg.add_attachment(
                    f.read(),
                    maintype="application",
                    subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename=os.path.basename(report_path)
                )

            with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=10.0) as s:
                s.starttls()
                s.login(smtp_user, smtp_pass)
                s.send_message(email_msg)

            status = "SENT_SMTP"
            msg = "DispatchAgent: Dispatched variance spreadsheet via SMTP."
        else:
            payload = {
                "event": "reconciliation_alert",
                "summary": subject,
                "discrepancies_count": discrepancy_count,
                "total_variance_chf": total_abs_variance,
                "report_file": os.path.basename(report_path),
                "items": discrepancies
            }
            res = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=8.0)
            res.raise_for_status()
            status = "SENT_WEBHOOK"
            msg = f"DispatchAgent: Posted webhook payload to {WEBHOOK_URL}."

    except Exception as err:
        status = "FAILED"
        msg = f"DispatchAgent Delivery Failure: {str(err)}"

    return {"dispatch_status": status, "messages": [HumanMessage(content=msg)]}


# ==============================================================================
# 5. GRAPH HARNESS ASSEMBLY
# ==============================================================================

def build_financial_pipeline():
    workflow = StateGraph(AgentState)

    workflow.add_node("reader_agent", reader_agent_node)
    workflow.add_node("storage_agent", storage_agent_node)
    workflow.add_node("reconciliation_agent", reconciliation_agent_node)
    workflow.add_node("reporting_agent", reporting_agent_node)
    workflow.add_node("dispatch_agent", dispatch_agent_node)

    workflow.add_edge(START, "reader_agent")
    workflow.add_edge("reader_agent", "storage_agent")
    workflow.add_edge("storage_agent", "reconciliation_agent")
    workflow.add_edge("reconciliation_agent", "reporting_agent")
    workflow.add_edge("reporting_agent", "dispatch_agent")
    workflow.add_edge("dispatch_agent", END)

    return workflow.compile()


# ==============================================================================
# 6. DEMO EXECUTION
# ==============================================================================

if __name__ == "__main__":
    init_database()

    # Create dummy Swiss bank CSV feed
    sample_csv = "test_feed.csv"
    with open(sample_csv, "w", encoding="utf-8") as f:
        f.write("28.10.2026;SUNRISE COMMUNICATIONS AG LAUSANNE;-89.90;CH-TX-001\n")
        f.write("29.10.2026;LOYER APPARTEMENT DUPLEX 1ER ETAGE;2'150.00;CH-TX-002\n")
        f.write("01.11.2026;SERVICES INDUSTRIELS DE GENEVE (SIG);-145.20;CH-TX-003\n")
        f.write("02.11.2026;UNEXPECTED CAFE RESTAURANT;-24.50;CH-TX-004\n")

    initial_input = {
        "raw_file_path": sample_csv,
        "transactions": [],
        "reconciliation_results": [],
        "db_status": "PENDING",
        "report_path": None,
        "dispatch_status": "PENDING",
        "messages": []
    }

    pipeline = build_financial_pipeline()
    final_output = pipeline.invoke(initial_input)

    print("\n================== PIPELINE AUDIT LOG ==================")
    for message in final_output["messages"]:
        print(f"[{message.type.upper()}] {message.content}")

    print("\n================== FINAL STATE SUMMARY =================")
    print(f"DB Status:       {final_output['db_status']}")
    print(f"Report File:     {final_output['report_path']}")
    print(f"Dispatch Status: {final_output['dispatch_status']}")
```

---

## 6. Environment Variables Reference

| Variable | Default Value | Description |
|---|---|---|
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | Primary local inference URL. |
| `DISPATCH_CHANNEL` | `webhook` | Dispatch protocol (`webhook` or `smtp`). |
| `DISPATCH_WEBHOOK_URL` | `https://httpbin.org/post` | Webhook target (Slack, Teams, etc.). |
| `DISPATCH_COUNT_THRESHOLD` | `1` | Minimum discrepancies required to trigger dispatch. |
| `DISPATCH_VARIANCE_THRESHOLD` | `50.00` | Minimum absolute cumulative variance to trigger dispatch. |
| `SMTP_HOST` | `smtp.gmail.com` | Outbound mail server hostname. |
| `SMTP_PORT` | `587` | Port for STARTTLS. |
| `SMTP_USER` | `""` | Sending email address. |
| `SMTP_PASS` | `""` | App-specific mail password. |
| `ALERT_TO_EMAIL` | `accounting@example.com` | Destination recipient address. |