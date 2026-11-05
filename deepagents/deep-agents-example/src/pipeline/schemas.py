from typing import Annotated, List, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
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


class AgentState(TypedDict):
    raw_file_path: str
    transactions: List[dict]
    reconciliation_results: List[dict]
    db_status: str
    report_path: Optional[str]
    dispatch_status: str  # PENDING, SENT_SMTP, SENT_WEBHOOK, SKIPPED_THRESHOLD, FAILED
    messages: Annotated[List[BaseMessage], add_messages]

