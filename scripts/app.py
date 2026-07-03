#!/usr/bin/env python
import argparse
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.service import ReceiptSystem
from core.reports import PnLReport, MonthlyExpenseReport, CashReconReport, export_receipts
from core.scanner import ReceiptScanner


def cmd_scan(args):
    scanner = ReceiptScanner()
    parsed = scanner.extract(args.image)
    receipt_id = scanner.save_receipt(args.image, parsed)
    print(f"Saved receipt id={receipt_id}")
    print(f"Date: {parsed.get('date')}")
    print(f"Supplier: {parsed.get('supplier')}")
    print(f"Total: {parsed.get('total_amount')}")
    print(f"Tax: {parsed.get('tax_amount')}")
    print(f"Payment: {parsed.get('payment_method')}")
    print(f"Items: {len(parsed.get('items', []))}")


def cmd_opening(args):
    system = ReceiptSystem()
    system.open_cash(args.date, args.amount, note=args.note or "")
    print(f"Opening cash set: {args.date} = {args.amount}")


def cmd_sale(args):
    system = ReceiptSystem()
    system.add_sale(args.amount, args.date, args.payment, note=args.note or "")
    system.refresh_daily_summary(args.date)
    print(f"Sale recorded: {args.date} {args.amount} ({args.payment})")


def cmd_expense(args):
    system = ReceiptSystem()
    system.add_expense(
        args.amount, args.date, args.category, payment_method=args.payment, note=args.note or ""
    )
    system.refresh_daily_summary(args.date)
    print(f"Expense recorded: {args.date} {args.amount} [{args.category}]")


def cmd_closing(args):
    system = ReceiptSystem()
    variance = system.close_cash(args.date, args.expected, args.actual, note=args.note or "")
    system.refresh_daily_summary(args.date)
    print(f"Closing: expected={args.expected}, actual={args.actual}, variance={variance}")


def cmd_pnl(args):
    rpt = PnLReport(args.start, args.end)
    out = rpt.export()
    print(rpt.profit_and_loss().to_string(index=False))
    print(f"\nExported: {out}")


def cmd_monthly(args):
    rpt = MonthlyExpenseReport()
    df = rpt.monthly(args.year)
    print(df.to_string(index=False))
    out = rpt.export(args.year)
    print(f"Exported: {out}")


def cmd_cash(args):
    rpt = CashReconReport()
    out = rpt.export(args.date)
    print(rpt.reconcile(args.date).to_string(index=False))
    print(f"Exported: {out}")


def cmd_receipts(_args):
    out = export_receipts()
    print(f"Exported receipts: {out}")


def cmd_db(_args):
    print(ReceiptSystem().db_path())


def main():
    p = argparse.ArgumentParser(description="Receipt Processing System")
    sub = p.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Scan receipt from image")
    scan.add_argument("image", help="Path to receipt image")

    op = sub.add_parser("opening", help="Set daily cash opening")
    op.add_argument("date")
    op.add_argument("amount", type=float)
    op.add_argument("--note", default="")

    sale = sub.add_parser("sale", help="Record a sale")
    sale.add_argument("date")
    sale.add_argument("amount", type=float)
    sale.add_argument("--payment", default="cash", choices=["cash", "card", "qr", "other"])
    sale.add_argument("--note", default="")

    exp = sub.add_parser("expense", help="Record an expense")
    exp.add_argument("date")
    exp.add_argument("amount", type=float)
    exp.add_argument("--category", default="other", choices=["bills", "supplies", "fuel", "maintenance", "rent", "utilities", "other"])
    exp.add_argument("--payment", default="cash", choices=["cash", "card", "qr", "other"])
    exp.add_argument("--note", default="")

    close = sub.add_parser("closing", help="Record daily cash closing")
    close.add_argument("date")
    close.add_argument("expected", type=float)
    close.add_argument("actual", type=float)
    close.add_argument("--note", default="")

    pnl = sub.add_parser("pnl", help="Profit & Loss report")
    pnl.add_argument("--start", required=True)
    pnl.add_argument("--end", default=date.today().isoformat())

    monthly = sub.add_parser("monthly", help="Monthly expense report")
    monthly.add_argument("year", type=int)

    cash = sub.add_parser("cash", help="Cash reconciliation")
    cash.add_argument("date")

    sub.add_parser("receipts", help="Export all receipts to Excel")
    sub.add_parser("db", help="Show database path")

    args = p.parse_args()
    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "opening":
        cmd_opening(args)
    elif args.command == "sale":
        cmd_sale(args)
    elif args.command == "expense":
        cmd_expense(args)
    elif args.command == "closing":
        cmd_closing(args)
    elif args.command == "pnl":
        cmd_pnl(args)
    elif args.command == "monthly":
        cmd_monthly(args)
    elif args.command == "cash":
        cmd_cash(args)
    elif args.command == "receipts":
        cmd_receipts(args)
    elif args.command == "db":
        cmd_db(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
