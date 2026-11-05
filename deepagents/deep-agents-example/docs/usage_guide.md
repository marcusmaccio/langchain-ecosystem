# Operational Usage Guide

This guide describes how to operate the financial pipeline, run different execution scenarios, provide custom input statements, and interpret audit reports.

---

## 1. Available Execution Modes

### Mode 1: Core Reconciliation Run (No Reports / No Alerts)
Use when you only need to ingest transactions and verify reconciliation against your expected invoice ledger:

```bash
.venv/bin/python run_core_pipeline.py
```

**Terminal Output Example:**
```
=================================================================
  RUNNING CORE 3-AGENT PIPELINE
  Input File: test_feed.csv
=================================================================

--- AGENT AUDIT MESSAGES ---
[HUMAN] ReaderAgent: Successfully parsed 4 transactions via local LLM.
[HUMAN] StorageAgent: Stored 4 transactions in bank_reconciliation.db.
[HUMAN] ReconciliationAgent: Processed 4 items. Exact: 2, Mismatch: 1, Unmatched: 1.

--- RECONCILIATION SUMMARY ---
• [EXACT_MATCH    ] TX: CH-TX-001  | Exp: EXP-UTIL-002 | Variance:   +0.00 | Exact match with EXP-UTIL-002 (SUNRISE COMMUNICATIONS)
• [EXACT_MATCH    ] TX: CH-TX-002  | Exp: EXP-RENT-001 | Variance:   +0.00 | Exact match with EXP-RENT-001 (LOYER APPARTEMENT DUPLEX)
• [AMOUNT_MISMATCH] TX: CH-TX-003  | Exp: EXP-POW-003  | Variance:   +4.80 | Partial match with EXP-POW-003. Variance: 4.8 CHF
• [UNMATCHED      ] TX: CH-TX-004  | Exp: NONE         | Variance:   +0.00 | No matching expected invoice found in ledger

--- STATE SUMMARY ---
Database Status:        COMMITTED
Transactions Processed: 4
Reconciled Items:       4
=================================================================
```

---

### Mode 2: Full End-to-End Pipeline
Executes all 5 agents, generating report files in `reports/` and dispatching threshold notifications:

```bash
# Run with default demo feed:
.venv/bin/python run_full_pipeline.py

# Run with a custom statement file:
.venv/bin/python run_full_pipeline.py --file statements/november_statement.csv

# Override dispatch channel from command line:
.venv/bin/python run_full_pipeline.py --channel smtp
```

---

### Mode 3: Instant Offline Dry-Run
Executes the full 5-agent pipeline in **<1 second** by mocking the Reader Agent's LLM response with representative Swiss bank data:

```bash
.venv/bin/python run_dry_run.py
```
This is ideal for CI/CD checks, demonstrations, or verifying reporting without having LM Studio open.

---

## 2. Supported Statement Formats

### CSV Statements
The Reader Agent detects delimiters automatically (`semicolon`, `comma`, etc.) and handles European/Swiss currency formatting (e.g. `2'150.00` or `-89.90`):

```csv
28.10.2026;SUNRISE COMMUNICATIONS AG LAUSANNE;-89.90;CH-TX-001
29.10.2026;LOYER APPARTEMENT DUPLEX 1ER ETAGE;2'150.00;CH-TX-002
01.11.2026;SERVICES INDUSTRIELS DE GENEVE (SIG);-145.20;CH-TX-003
02.11.2026;UNEXPECTED CAFE RESTAURANT;-24.50;CH-TX-004
```

### PDF Statements
For bank statement PDFs, `extract_pdf_bank_statement` extracts text across pages, feeding raw transaction blocks into the Reader Agent.

Run against a PDF statement:
```bash
.venv/bin/python run_full_pipeline.py --file my_bank_statement.pdf
```

---

## 3. Inspecting Reports & Ledger

### Variance Reports
When discrepancies exist (`AMOUNT_MISMATCH` or `UNMATCHED`), files are saved in `reports/`:
- `reports/variance_summary_<TIMESTAMP>.csv`: Semicolon-delimited UTF-8 CSV.
- `reports/variance_summary_<TIMESTAMP>.xlsx`: Excel workbook formatted with auto-fitted column widths.

Columns included:
- `Transaction ID`
- `Status`
- `Booking Date`
- `Description`
- `Actual Amount`
- `Expected ID`
- `Variance`
- `Currency`
- `Audit Notes`

### SQLite Ledger Querying
Query transaction records:
```bash
sqlite3 bank_reconciliation.db -header -column "SELECT * FROM transactions LIMIT 5;"
```

Query expected commitments:
```bash
sqlite3 bank_reconciliation.db -header -column "SELECT * FROM expected_invoices;"
```

---

## 4. Troubleshooting & FAQ

### Issue: "LM Studio offline at http://localhost:1234/v1"
- Ensure LM Studio is open and the Local Server is turned **ON** in the Developer tab.
- Check that the model is loaded into memory (green status indicator).

### Issue: "Error code: 400 - response_format.type must be json_schema or text"
- This occurs when older OpenAI clients enforce `{"type": "json_object"}`. Our implementation in `src/pipeline/llm.py` automatically handles this by letting the model output JSON natively according to system prompt instructions.

### Issue: LLM request times out after 60s
- 27B reasoning models spend tokens thinking in `reasoning_content` before emitting JSON.
- Increase the timeout if needed:
  ```bash
  export LM_STUDIO_TIMEOUT=240.0
  ```

