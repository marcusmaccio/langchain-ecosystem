"""
Agent 4: Variance Reporting Agent
File: src/pipeline/agents/reporting_agent.py

Filters exception records (AMOUNT_MISMATCH, UNMATCHED) and generates
auditable CSV and formatted Excel (.xlsx) spreadsheets with auto-fitted columns.
"""

import os
from datetime import datetime
from typing import Optional
import pandas as pd
from langchain_core.messages import HumanMessage
from src.pipeline.schemas import AgentState


class ReportingAgent:
    """
    Agent 4: Generates audit exception files (CSV and formatted Excel)
    for all transactions with discrepancies.
    """

    def __init__(self, reports_dir: Optional[str] = None):
        self._reports_dir = reports_dir

    @property
    def reports_dir(self) -> str:
        return self._reports_dir or os.getenv("REPORTS_DIR", "reports")

    def build_report_rows(self, discrepancies: list[dict], transactions: list[dict]) -> list[dict]:
        tx_map = {t["transaction_id"]: t for t in transactions}
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
                "Audit Notes": item.get("notes", ""),
            })
        return report_rows

    def export_reports(self, df: pd.DataFrame) -> tuple[str, str]:
        os.makedirs(self.reports_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(self.reports_dir, f"variance_summary_{timestamp}.csv")
        xlsx_path = os.path.join(self.reports_dir, f"variance_summary_{timestamp}.xlsx")

        df.to_csv(csv_path, index=False, sep=";", encoding="utf-8-sig")

        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Variances", index=False)
            worksheet = writer.sheets["Variances"]
            for col in worksheet.columns:
                max_len = max(len(str(c.value or "")) for c in col)
                worksheet.column_dimensions[col[0].column_letter].width = max(max_len + 3, 12)

        return csv_path, xlsx_path

    def run(self, state: AgentState) -> dict:
        recon = state.get("reconciliation_results", [])
        discrepancies = [r for r in recon if r["status"] in ("AMOUNT_MISMATCH", "UNMATCHED")]

        if not discrepancies:
            return {
                "report_path": None,
                "messages": [HumanMessage(content="ReportingAgent: Zero discrepancies. No report required.")],
            }

        rows = self.build_report_rows(discrepancies, state.get("transactions", []))
        df = pd.DataFrame(rows)
        csv_path, xlsx_path = self.export_reports(df)

        msg = f"ReportingAgent: Exported exception files:\n  - CSV: {csv_path}\n  - Excel: {xlsx_path}"
        return {"report_path": xlsx_path, "messages": [HumanMessage(content=msg)]}


def reporting_agent_node(state: AgentState) -> dict:
    """LangGraph node function for ReportingAgent."""
    agent = ReportingAgent()
    return agent.run(state)

