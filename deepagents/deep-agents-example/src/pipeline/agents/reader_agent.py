"""
Agent 1: Reader & Normalizer Agent
File: src/pipeline/agents/reader_agent.py

Ingests raw, unstructured financial statements (CSV, PDF), extracts text,
pings LM Studio for health, and normalizes transactions into strict Pydantic records.
"""

import csv
import json
import os
from typing import Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pypdf import PdfReader

from src.pipeline.llm import extract_json_from_response, get_resilient_lm_studio_client
from src.pipeline.schemas import AgentState, CleanTransaction, TransactionBatch


@tool
def read_raw_csv_content(file_path: str) -> str:
    """Reads raw CSV content with automatic delimiter sniffing."""
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


class ReaderAgent:
    """
    Agent 1: Ingests unstructured financial statements and normalizes
    them into validated CleanTransaction objects using a local LLM.
    """

    def __init__(self, llm_client=None):
        self._llm_client = llm_client

    def extract_text(self, file_path: str) -> tuple[Optional[str], Optional[str]]:
        """Extracts text from CSV or PDF file."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            return read_raw_csv_content.invoke({"file_path": file_path}), None
        elif ext == ".pdf":
            return extract_pdf_bank_statement.invoke({"file_path": file_path}), None
        else:
            return None, f"ReaderAgent: Unsupported format '{ext}'"

    def get_system_prompt(self) -> str:
        schema_def = json.dumps(TransactionBatch.model_json_schema(), indent=2)
        return (
            "You are an offline bank statement ingestion agent.\n"
            "Output ONLY a raw JSON object strictly adhering to this JSON Schema:\n"
            f"{schema_def}\n\n"
            "Rules:\n"
            "1. Dates must strictly follow YYYY-MM-DD.\n"
            "2. Parse amounts as signed floats (debits negative, credits positive).\n"
            "3. Strip internal transaction noise from descriptions.\n"
            "4. Default currency to CHF if not specified."
        )

    def run(self, state: AgentState) -> dict:
        file_path = state["raw_file_path"]
        raw_text, error = self.extract_text(file_path)
        if error:
            return {
                "transactions": [],
                "messages": [HumanMessage(content=error)],
            }

        try:
            llm = self._llm_client or get_resilient_lm_studio_client()
        except ConnectionError as err:
            return {
                "transactions": [],
                "messages": [HumanMessage(content=f"ReaderAgent ABORT: {str(err)}")],
            }

        system_prompt = self.get_system_prompt()

        try:
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Raw Bank Statement:\n\n{raw_text}"),
            ])
            content = response.content if isinstance(response.content, str) else str(response.content)
            content = extract_json_from_response(content)

            batch = TransactionBatch.model_validate(json.loads(content))
            records = [item.model_dump() for item in batch.items]
            msg = f"ReaderAgent: Successfully parsed {len(records)} transactions via local LLM."
        except Exception as e:
            records = []
            msg = f"ReaderAgent Parsing Error: {str(e)}"

        return {"transactions": records, "messages": [HumanMessage(content=msg)]}


def reader_agent_node(state: AgentState) -> dict:
    """LangGraph node function for ReaderAgent."""
    agent = ReaderAgent()
    return agent.run(state)

