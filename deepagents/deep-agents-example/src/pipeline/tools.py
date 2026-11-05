import csv
import os
from langchain_core.tools import tool
from pypdf import PdfReader


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

