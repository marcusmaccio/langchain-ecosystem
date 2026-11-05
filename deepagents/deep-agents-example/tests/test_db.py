import sqlite3
from src.pipeline.db import init_database


def test_init_database(tmp_path):
    db_file = str(tmp_path / "test.db")
    init_database(db_file)

    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        assert "transactions" in tables
        assert "expected_invoices" in tables

        cursor.execute("SELECT COUNT(*) FROM expected_invoices;")
        count = cursor.fetchone()[0]
        assert count == 3

