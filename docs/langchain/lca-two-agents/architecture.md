# Stage 2 Architecture — Reused BTA + Accounting Agent (`lca-two-agents`)

## Two-Agent Pipeline Flow

```mermaid
flowchart LR
    PDFs["Bank Statement PDFs\n(One-shot or --watch 15m)"] --> BTA["Agent 1: BTA\n(Reused from lca-single-agent)"]
    BTA -->|1. Delivers| TxJSON["reports/transactions.json\n+ reports/transactions.html"]
    BTA -->|2. Calls notify_accounting_agent\n(Only when running with AA)| AA["Agent 2: Accounting Agent (AA)\n(src/accounting_agent.py)"]
    TxJSON --> AA
    AA -->|3. Creates Expandable Balance Page| BalHTML["reports/balance.html\n+ reports/balance.json"]
```

---

## Accounting Agent (AA) Responsibilities & Schemas

1. **Reading BTA Output (`read_bta_transactions_json`)**:
   - Reads `reports/transactions.json` delivered by BTA and inspects every transaction along with its `bank_name` and `bank_account`.
2. **Computing Per-Account Balances (`AccountBalanceGroup` & `BalanceSummary`)**:
   - Splits each transaction into:
     - `incoming`: Positive amount when `amount > 0` (else `0.0`)
     - `expense`: Positive amount `abs(amount)` when `amount < 0` (else `0.0`)
   - Aggregates `total_incoming`, `total_expenses`, and `net_balance` both globally (`BalanceSummary`) and per `(bank_name, bank_account)` (`AccountBalanceGroup`).
3. **Rendering Expandable Balance Sheet (`generate_balance_webpage`)**:
   - Writes structured accounting data to `reports/balance.json`.
   - Renders `reports/balance.html` featuring:
     - Top summary cards (`Banks & Accounts`, `Read PDF Files` modal trigger, `Total Incoming`, `Total Expenses`, `Net Balance`).
     - Expandable `<details class="account-section">` per Bank & Bank Account where the header + summary badges (`Entries`, `Incoming`, `Expenses`, `Net Balance`) are always visible and expand on click to show the 6-column Balance table (`#`, `Date`, `Description`, `Incoming`, `Expenses`, `Source PDF` with clickable `file://` links).
