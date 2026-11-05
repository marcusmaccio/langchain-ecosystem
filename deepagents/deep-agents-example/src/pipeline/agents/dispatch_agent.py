"""
Agent 5: Automated Dispatch Agent
File: src/pipeline/agents/dispatch_agent.py

Evaluates discrepancy count and cumulative absolute variance against configurable thresholds,
dispatching alerts via Webhook (POST JSON) or SMTP (Email with .xlsx attachment).
"""

import os
import smtplib
from email.message import EmailMessage
from typing import Optional
import requests
from langchain_core.messages import HumanMessage
from src.pipeline.schemas import AgentState


class DispatchAgent:
    """
    Agent 5: Automated notification agent that monitors discrepancy thresholds
    and triggers Webhook or SMTP email alerts.
    """

    def __init__(
        self,
        count_threshold: Optional[int] = None,
        variance_threshold: Optional[float] = None,
        channel: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        self._count_threshold = count_threshold
        self._variance_threshold = variance_threshold
        self._channel = channel
        self._webhook_url = webhook_url

    @property
    def count_threshold(self) -> int:
        if self._count_threshold is not None:
            return self._count_threshold
        return int(os.getenv("DISPATCH_COUNT_THRESHOLD", "1"))

    @property
    def variance_threshold(self) -> float:
        if self._variance_threshold is not None:
            return self._variance_threshold
        return float(os.getenv("DISPATCH_VARIANCE_THRESHOLD", "50.00"))

    @property
    def channel(self) -> str:
        return (self._channel or os.getenv("DISPATCH_CHANNEL", "webhook")).lower()

    @property
    def webhook_url(self) -> str:
        return self._webhook_url or os.getenv("DISPATCH_WEBHOOK_URL", "https://httpbin.org/post")

    def evaluate_thresholds(self, discrepancies: list[dict]) -> tuple[bool, int, float]:
        total_abs_variance = sum(abs(r.get("variance", 0.0)) for r in discrepancies)
        discrepancy_count = len(discrepancies)
        breached = (
            discrepancy_count >= self.count_threshold or
            total_abs_variance >= self.variance_threshold
        )
        return breached, discrepancy_count, total_abs_variance

    def send_smtp(self, subject: str, body: str, report_path: str):
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")
        to_email = os.getenv("ALERT_TO_EMAIL", "accounting@example.com")

        if not smtp_user or not smtp_pass:
            raise ValueError("SMTP credentials missing.")

        email_msg = EmailMessage()
        email_msg["Subject"] = subject
        email_msg["From"] = smtp_user
        email_msg["To"] = to_email
        email_msg.set_content(body)

        with open(report_path, "rb") as f:
            email_msg.add_attachment(
                f.read(),
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=os.path.basename(report_path),
            )

        host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=10.0) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(email_msg)

    def send_webhook(self, subject: str, discrepancies: list[dict], count: int, variance: float, report_path: str):
        payload = {
            "event": "reconciliation_alert",
            "summary": subject,
            "discrepancies_count": count,
            "total_variance_chf": variance,
            "report_file": os.path.basename(report_path),
            "items": discrepancies,
        }
        res = requests.post(self.webhook_url, json=payload, headers={"Content-Type": "application/json"}, timeout=8.0)
        res.raise_for_status()

    def run(self, state: AgentState) -> dict:
        report_path = state.get("report_path")
        recon = state.get("reconciliation_results", [])
        discrepancies = [r for r in recon if r["status"] in ("AMOUNT_MISMATCH", "UNMATCHED")]

        breached, count, total_variance = self.evaluate_thresholds(discrepancies)

        if not report_path or not breached:
            msg = (
                f"DispatchAgent: Threshold not reached (Count: {count} < {self.count_threshold}, "
                f"Variance: {total_variance:.2f} < {self.variance_threshold:.2f}). Notification omitted."
            )
            return {"dispatch_status": "SKIPPED_THRESHOLD", "messages": [HumanMessage(content=msg)]}

        subject = f"[Action Required] Bank Reconciliation Variance Alert ({count} discrepancies)"
        body = (
            f"Reconciliation exception summary:\n"
            f"- Discrepancies Count: {count}\n"
            f"- Cumulative Absolute Variance: {total_variance:.2f} CHF\n"
            f"- Report File: {os.path.basename(report_path)}"
        )

        try:
            if self.channel == "smtp":
                self.send_smtp(subject, body, report_path)
                status = "SENT_SMTP"
                msg = "DispatchAgent: Dispatched variance spreadsheet via SMTP."
            else:
                self.send_webhook(subject, discrepancies, count, total_variance, report_path)
                status = "SENT_WEBHOOK"
                msg = f"DispatchAgent: Posted webhook payload to {self.webhook_url}."
        except Exception as err:
            status = "FAILED"
            msg = f"DispatchAgent Delivery Failure: {str(err)}"

        return {"dispatch_status": status, "messages": [HumanMessage(content=msg)]}


def dispatch_agent_node(state: AgentState) -> dict:
    """LangGraph node function for DispatchAgent."""
    agent = DispatchAgent()
    return agent.run(state)

