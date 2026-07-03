import sqlite3
from pathlib import Path
from datetime import datetime, date

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "receipts.db"

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    contact TEXT,
    category TEXT CHECK(category IN ('bills','supplies','fuel','maintenance','rent','utilities','other')),
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    role TEXT CHECK(role IN ('cashier','manager','supervisor','other')),
    phone TEXT,
    email TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS cash_openings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    opening_balance REAL NOT NULL DEFAULT 0,
    opened_by INTEGER,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    payment_method TEXT CHECK(payment_method IN ('cash','card','qr','other')),
    receipt_id INTEGER,
    recorded_by INTEGER,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT CHECK(category IN ('bills','supplies','fuel','maintenance','rent','utilities','other')),
    supplier_id INTEGER,
    staff_id INTEGER,
    payment_method TEXT CHECK(payment_method IN ('cash','card','qr','other')),
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    date TEXT,
    supplier_id INTEGER,
    total_amount REAL,
    tax_amount REAL DEFAULT 0,
    payment_method TEXT,
    ocr_text TEXT,
    status TEXT CHECK(status IN ('pending','processed','failed','review')) DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
);

CREATE TABLE IF NOT EXISTS receipt_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    quantity REAL DEFAULT 1,
    unit_price REAL,
    total_price REAL,
    category TEXT CHECK(category IN ('food','beverage','supplies','fuel','maintenance','other')),
    FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cash_closings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    expected_balance REAL NOT NULL DEFAULT 0,
    actual_balance REAL NOT NULL DEFAULT 0,
    variance REAL DEFAULT 0,
    closed_by INTEGER,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS daily_summary (
    date TEXT PRIMARY KEY,
    total_sales REAL DEFAULT 0,
    total_expenses REAL DEFAULT 0,
    cash_opening REAL DEFAULT 0,
    cash_closing REAL DEFAULT 0,
    cash_variance REAL DEFAULT 0,
    profit REAL DEFAULT 0,
    transaction_count INTEGER DEFAULT 0,
    receipt_count INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(date);
CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status);
CREATE INDEX IF NOT EXISTS idx_receipt_items_receipt ON receipt_items(receipt_id);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    print(f"Database initialized at: {DB_PATH}")


if __name__ == "__main__":
    init_db()
