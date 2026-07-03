from pathlib import Path
from typing import Optional
from datetime import date

from .schema import get_connection, init_db, DB_PATH


class ReceiptSystem:
    def __init__(self):
        init_db()

    def add_supplier(self, name: str, category: str = "bills", contact: str = ""):
        with get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO suppliers(name,category,contact) VALUES(?,?,?)", (name, category, contact))
            conn.commit()

    def add_staff(self, full_name: str, role: str = "staff", phone: str = "", email: str = ""):
        with get_connection() as conn:
            conn.execute("INSERT INTO staff(full_name,role,phone,email,is_active) VALUES(?,?,?,?,1)", (full_name, role, phone, email))
            conn.commit()

    def open_cash(self, cash_date: str, amount: float, staff_id: Optional[int] = None, note: str = ""):
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cash_openings(date,opening_balance,opened_by,note)
                VALUES(?,?,?,?)
                ON CONFLICT(date) DO UPDATE SET opening_balance=excluded.opening_balance
                """,
                (cash_date, amount, staff_id, note),
            )
            conn.commit()

    def add_sale(self, amount: float, sale_date: str, payment_method: str = "cash", staff_id: Optional[int] = None, note: str = "", receipt_id: Optional[int] = None):
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sales(date,amount,payment_method,recorded_by,note,receipt_id) VALUES(?,?,?,?,?,?)",
                (sale_date, amount, payment_method, staff_id, note, receipt_id),
            )
            conn.commit()

    def add_expense(self, amount: float, expense_date: str, category: str = "other", supplier_id: Optional[int] = None,
                    staff_id: Optional[int] = None, payment_method: str = "cash", note: str = ""):
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO expenses(date,amount,category,supplier_id,staff_id,payment_method,note)
                VALUES(?,?,?,?,?,?,?)
                """,
                (expense_date, amount, category, supplier_id, staff_id, payment_method, note),
            )
            conn.commit()

    def close_cash(self, cash_date: str, expected: float, actual: float, staff_id: Optional[int] = None, note: str = ""):
        variance = round(actual - expected, 4)
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cash_closings(date,expected_balance,actual_balance,variance,closed_by,note)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(date) DO UPDATE SET expected_balance=excluded.expected_balance,actual_balance=excluded.actual_balance,variance=excluded.variance
                """,
                (cash_date, expected, actual, variance, staff_id, note),
            )
            conn.commit()
        return variance

    def ensure_daily_summary(self, day: Optional[str] = None):
        day = day or date.today().isoformat()
        with get_connection() as conn:
            cur = conn.execute("SELECT date FROM daily_summary WHERE date=?", (day,))
            if not cur.fetchone():
                conn.execute("INSERT INTO daily_summary(date) VALUES(?)", (day,))
                conn.commit()

    def refresh_daily_summary(self, day: str):
        self.ensure_daily_summary(day)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE daily_summary SET
                    total_sales = (SELECT COALESCE(SUM(amount),0) FROM sales WHERE date=?),
                    total_expenses = (SELECT COALESCE(SUM(amount),0) FROM expenses WHERE date=?),
                    cash_closing = (SELECT actual_balance FROM cash_closings WHERE date=?),
                    cash_variance = (SELECT variance FROM cash_closings WHERE date=?),
                    profit = (SELECT COALESCE(SUM(amount),0) FROM sales WHERE date=?) -
                             (SELECT COALESCE(SUM(amount),0) FROM expenses WHERE date=?),
                    transaction_count = (SELECT COUNT(*) FROM sales WHERE date=?) + (SELECT COUNT(*) FROM expenses WHERE date=?),
                    receipt_count = (SELECT COUNT(*) FROM receipts WHERE date=?),
                    updated_at = datetime('now','localtime')
                WHERE date=?
                """,
                (day, day, day, day, day, day, day, day, day, day),
            )
            conn.commit()

    def list_receipts(self, status: Optional[str] = None) -> list[dict]:
        with get_connection() as conn:
            if status:
                return [dict(r) for r in conn.execute("SELECT * FROM receipts WHERE status=? ORDER BY date DESC", (status,)).fetchall()]
            return [dict(r) for r in conn.execute("SELECT * FROM receipts ORDER BY date DESC").fetchall()]

    def db_path(self) -> str:
        return str(DB_PATH)
