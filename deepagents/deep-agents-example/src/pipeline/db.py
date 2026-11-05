import os
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = "bank_reconciliation.db"


def get_db_path(custom_path: Optional[str] = None) -> str:
    """Returns the effective database path."""
    return custom_path or os.getenv("DB_PATH", DEFAULT_DB_PATH)


def init_database(db_path: Optional[str] = None) -> str:
    """Initializes tables and seeds test expectations if empty."""
    target_path = get_db_path(db_path)
    with sqlite3.connect(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expected_invoices (
                expected_id TEXT PRIMARY KEY,
                party_name TEXT NOT NULL,
                expected_amount REAL NOT NULL,
                due_date TEXT NOT NULL,
                currency TEXT NOT NULL
            );
        """)
        cursor.execute("SELECT COUNT(*) FROM expected_invoices;")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("""
                INSERT INTO expected_invoices (expected_id, party_name, expected_amount, due_date, currency)
                VALUES (?, ?, ?, ?, ?);
            """, [
                ("EXP-RENT-001", "LOYER APPARTEMENT DUPLEX", 2150.00, "2026-10-31", "CHF"),
                ("EXP-UTIL-002", "SUNRISE COMMUNICATIONS", -89.90, "2026-10-30", "CHF"),
                ("EXP-POW-003", "SERVICES INDUSTRIELS DE GENEVE", -150.00, "2026-11-05", "CHF")
            ])
        conn.commit()
    return target_path

