from src.pipeline.tools import read_raw_csv_content, extract_pdf_bank_statement


def test_read_raw_csv_content(tmp_path):
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text("date;desc;amount\n2026-10-31;Test;100.00\n", encoding="utf-8")

    result = read_raw_csv_content.invoke({"file_path": str(csv_file)})
    assert "ROW 0:" in result
    assert "Test" in result


def test_read_csv_not_found():
    result = read_raw_csv_content.invoke({"file_path": "non_existent.csv"})
    assert "Error: File" in result


def test_extract_pdf_not_found():
    result = extract_pdf_bank_statement.invoke({"file_path": "non_existent.pdf"})
    assert "Error: File" in result

