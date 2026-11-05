# Configuration Reference

This document describes all environment variables, model configurations, database paths, and dispatch settings available in the pipeline.

---

## 1. Environment Variables Overview

All settings can be customized using environment variables or defined in a `.env` file in the project root:

| Variable | Default Value | Description |
|---|---|---|
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | Primary endpoint for local LM Studio inference. |
| `LM_STUDIO_FALLBACK_URL` | `http://192.168.1.21:1234/v1` | LAN fallback if localhost is unreachable. |
| `LM_STUDIO_MODEL` | `qwen3.8-27b-uncensored-mlx` | Loaded model identifier in LM Studio. |
| `LM_STUDIO_TIMEOUT` | `180.0` | Request timeout in seconds (allows reasoning token generation). |
| `LM_STUDIO_RESPONSE_FORMAT`| *(unset)* | Optional response format type override (e.g. `{"type": "json_schema", ...}`). |
| `DB_PATH` | `bank_reconciliation.db` | Path to the SQLite ledger database. |
| `REPORTS_DIR` | `reports` | Output directory for generated CSV and Excel variance files. |
| `DISPATCH_CHANNEL` | `webhook` | Alert dispatch mechanism: `webhook` or `smtp`. |
| `DISPATCH_WEBHOOK_URL` | `https://httpbin.org/post` | Webhook HTTP POST target (Slack, Discord, Teams, custom). |
| `DISPATCH_COUNT_THRESHOLD` | `1` | Minimum number of discrepancies required to fire an alert. |
| `DISPATCH_VARIANCE_THRESHOLD`| `50.00` | Minimum cumulative absolute variance (in CHF) to trigger alert. |
| `SMTP_HOST` | `smtp.gmail.com` | Outbound SMTP server hostname. |
| `SMTP_PORT` | `587` | Outbound SMTP TLS port. |
| `SMTP_USER` | `""` | Sending email address. |
| `SMTP_PASS` | `""` | Sending email application-specific password. |
| `ALERT_TO_EMAIL` | `accounting@example.com` | Destination email address for discrepancy alerts. |

---

## 2. LM Studio Engine Settings

Recommended configuration for Apple Silicon:

- **Context Length ($n_{\text{ctx}}$)**: $\ge 16384$ tokens.
- **Metal Acceleration**: 100% GPU offload on Apple Silicon Unified Memory.
- **Temperature**: `0.1` (ensures stable, deterministic extraction).
- **Top P**: `0.85`.
- **System Prompt**: Enforces strict JSON output with `items` list schema.

---

## 3. Dispatch Configuration Examples

### Example A: Webhook (Slack / Teams / Custom API)

```bash
export DISPATCH_CHANNEL=webhook
export DISPATCH_WEBHOOK_URL="https://hooks.slack.com/services/T00/B00/XXXXX"
export DISPATCH_COUNT_THRESHOLD=1
export DISPATCH_VARIANCE_THRESHOLD=20.00
```

The dispatched webhook payload is a structured JSON:
```json
{
  "event": "reconciliation_alert",
  "summary": "[Action Required] Bank Reconciliation Variance Alert (2 discrepancies)",
  "discrepancies_count": 2,
  "total_variance_chf": 4.80,
  "report_file": "variance_summary_20261104_212230.xlsx",
  "items": [
    {
      "transaction_id": "CH-TX-003",
      "expected_id": "EXP-POW-003",
      "status": "AMOUNT_MISMATCH",
      "variance": 4.80,
      "notes": "Partial match with EXP-POW-003. Variance: 4.8 CHF"
    }
  ]
}
```

### Example B: Outbound SMTP Email with Excel Attachment

```bash
export DISPATCH_CHANNEL=smtp
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT=587
export SMTP_USER="notifications@mycompany.ch"
export SMTP_PASS="your-app-password"
export ALERT_TO_EMAIL="cfo@mycompany.ch"
```

The dispatch agent will attach the generated `.xlsx` spreadsheet directly to the email.

---

## 4. Custom Database Location

To use a separate database file or run tests against an isolated SQLite database:

```bash
export DB_PATH="data/ledger_production.db"
```
The database and tables will be initialized automatically on the first pipeline run.

