"""
Reports + Excel export modules.
Usage:
    from core.reports import PnLReport, MonthlyExpenseReport, CashReconReport
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from .schema import get_connection

EXPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _to_df(sql: str, params: tuple = None) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


class PnLReport:
    def __init__(self, start: str, end: Optional[str] = None):
        self.start = start
        self.end = end or date.today().isoformat()

    def profit_and_loss(self) -> pd.DataFrame:
        sales = _to_df(
            "SELECT date, SUM(amount) as amount FROM sales WHERE date BETWEEN ? AND ? GROUP BY date",
            (self.start, self.end),
        )
        expenses = _to_df(
            "SELECT date, SUM(amount) as amount FROM expenses WHERE date BETWEEN ? AND ? GROUP BY date",
            (self.start, self.end),
        )
        all_dates = pd.DataFrame({"date": pd.date_range(self.start, self.end, freq="D").astype(str)})
        df_s = all_dates.merge(sales, on="date", how="left").fillna({"amount": 0.0})
        df_s.rename(columns={"amount": "sales"}, inplace=True)
        df_e = all_dates.merge(expenses, on="date", how="left").fillna({"amount": 0.0})
        df_e.rename(columns={"amount": "expenses"}, inplace=True)
        report = pd.merge(df_s, df_e, on="date", how="outer").fillna(0)
        report["profit"] = report["sales"] - report["expenses"]
        report["period"] = pd.to_datetime(report["date"]).dt.to_period("D").astype(str)
        return report[["period", "sales", "expenses", "profit"]].sort_values("period")

    def export(self, path: Optional[str | Path] = None) -> Path:
        df = self.profit_and_loss()
        out = Path(path) if path else EXPORT_DIR / f"pnl_{self.start}_to_{self.end}.xlsx"
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="ProfitAndLoss", index=False)
            self._write_summary(writer, df, "Summary")
        return out

    def _write_summary(self, writer: pd.ExcelWriter, df: pd.DataFrame, sheet_name: str):
        summary = pd.DataFrame(
            {
                "Metric": ["Total Sales", "Total Expenses", "Net Profit", "Start", "End"],
                "Value": [df["sales"].sum(), df["expenses"].sum(), df["profit"].sum(), self.start, self.end],
            }
        )
        summary.to_excel(writer, sheet_name=sheet_name, index=False)


class MonthlyExpenseReport:
    def monthly(self, year: int) -> pd.DataFrame:
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        sql = """
            SELECT strftime('%Y-%m',date) as month, category, SUM(amount) as amount
            FROM expenses WHERE date BETWEEN ? AND ?
            GROUP BY month, category ORDER BY month
        """
        df = _to_df(sql, (start, end))
        return df if not df.empty else pd.DataFrame(columns=["month", "category", "amount"])

    def export(self, year: int, path: Optional[str | Path] = None) -> Path:
        df = self.monthly(year)
        out = Path(path) if path else EXPORT_DIR / f"monthly_expenses_{year}.xlsx"
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="MonthlyExpenses", index=False)
        return out


class CashReconReport:
    def reconcile(self, target_date: str) -> pd.DataFrame:
        sql = """
            SELECT
                :d as date,
                COALESCE((SELECT opening_balance FROM cash_openings WHERE date=:d),0) as opening_balance,
                COALESCE((SELECT SUM(amount) FROM sales WHERE date=:d),0) as sales,
                COALESCE((SELECT SUM(amount) FROM expenses WHERE date=:d),0) as expenses,
                COALESCE((SELECT expected_balance FROM cash_closings WHERE date=:d),0) as expected_balance,
                COALESCE((SELECT actual_balance FROM cash_closings WHERE date=:d),0) as actual_balance,
                COALESCE((SELECT variance FROM cash_closings WHERE date=:d),0) as variance,
                COALESCE((SELECT note FROM cash_closings WHERE date=:d),'') as note
        """
        return _to_df(sql, {"d": target_date})

    def export(self, target_date: str, path: Optional[str | Path] = None) -> Path:
        df = self.reconcile(target_date)
        out = Path(path) if path else EXPORT_DIR / f"cash_recon_{target_date}.xlsx"
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="CashReconciliation", index=False)
        return out


def export_receipts(path: Optional[str | Path] = None) -> Path:
    df = _to_df(
        """
        SELECT r.id, r.date, r.file_name, COALESCE(s.name,'-') as supplier,
               r.total_amount, r.tax_amount, r.payment_method, r.status, r.created_at
        FROM receipts r
        LEFT JOIN suppliers s ON s.id = r.supplier_id
        ORDER BY r.date DESC, r.id DESC
    """
    )
    out = Path(path) if path else EXPORT_DIR / f"receipts_all_{date.today().isoformat()}.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Receipts", index=False)
        items = _to_df(
            """
            SELECT ri.receipt_id, ri.item_name, ri.quantity, ri.unit_price, ri.total_price, ri.category
            FROM receipt_items ri
            ORDER BY ri.receipt_id DESC
        """
        )
        items.to_excel(writer, sheet_name="ReceiptItems", index=False)
    return out
