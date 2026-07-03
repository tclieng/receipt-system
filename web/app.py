from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from pathlib import Path
from datetime import date, datetime
import sqlite3
import sys

project_root = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(project_root))
from core.service import ReceiptSystem
from core.reports import PnLReport, MonthlyExpenseReport, CashReconReport, export_receipts
from core.scanner import ReceiptScanner

app = Flask(__name__)
app.secret_key = "receipt-system-secret"
app.config["UPLOAD_FOLDER"] = project_root / "data" / "uploads"
app.config["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)

system = ReceiptSystem()

# Reusable date helpers
today = date.today()

# Cache scanner — EasyOCR model download/init is expensive
_scanner = None

def get_scanner():
    global _scanner
    if _scanner is None:
        _scanner = ReceiptScanner()
    return _scanner


def get_db():
    from core.schema import get_connection
    return get_connection()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    db = get_db()
    today = date.today().isoformat()
    row = db.execute("SELECT * FROM daily_summary WHERE date=?", (today,)).fetchone()
    summary = dict(row) if row else None
    recent = db.execute("SELECT * FROM receipts ORDER BY date DESC LIMIT 10").fetchall()
    return render_template("dashboard.html", summary=summary, recent=recent)


@app.route("/receipts", methods=["GET", "POST"])
def receipts():
    db = get_db()
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("No file selected", "error")
            return redirect(request.url)
        save_path = app.config["UPLOAD_FOLDER"] / file.filename
        file.save(str(save_path))
        try:
            scanner = get_scanner()
            parsed = scanner.extract(str(save_path))
            receipt_id = scanner.save_receipt(str(save_path), parsed)
            flash(f"Receipt uploaded and scanned. Saved as ID {receipt_id}", "success")
        except Exception as e:
            flash(f"Scan failed: {e}", "error")
        return redirect(url_for("receipts"))
    rows = db.execute("""
        SELECT r.id, r.date, r.file_name, COALESCE(s.name,'-') as supplier,
               r.total_amount, r.tax_amount, r.payment_method, r.status, r.created_at
        FROM receipts r LEFT JOIN suppliers s ON s.id = r.supplier_id
        ORDER BY r.date DESC, r.id DESC
    """).fetchall()
    return render_template("receipts.html", receipts=rows, today=today.isoformat())


@app.route("/sales", methods=["GET", "POST"])
def sales():
    db = get_db()
    if request.method == "POST":
        system.add_sale(
            float(request.form["amount"]),
            request.form["date"],
            request.form.get("payment", "cash"),
            note=request.form.get("note", ""),
        )
        system.refresh_daily_summary(request.form["date"])
        flash("Sale recorded", "success")
        return redirect(url_for("sales"))
    rows = db.execute("SELECT * FROM sales ORDER BY date DESC LIMIT 200").fetchall()
    return render_template("sales.html", sales=rows, today=today.isoformat())


@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    db = get_db()
    if request.method == "POST":
        system.add_expense(
            float(request.form["amount"]),
            request.form["date"],
            category=request.form.get("category", "other"),
            payment_method=request.form.get("payment", "cash"),
            note=request.form.get("note", ""),
        )
        system.refresh_daily_summary(request.form["date"])
        flash("Expense recorded", "success")
        return redirect(url_for("expenses"))
    rows = db.execute("""
        SELECT e.*, COALESCE(s.name,'-') as supplier
        FROM expenses e LEFT JOIN suppliers s ON s.id = e.supplier_id
        ORDER BY e.date DESC LIMIT 200
    """).fetchall()
    return render_template("expenses.html", expenses=rows, today=today.isoformat())


@app.route("/cash", methods=["GET", "POST"])
def cash():
    db = get_db()
    if request.method == "POST":
        kind = request.form.get("kind")
        d = request.form["date"]
        if kind == "opening":
            system.open_cash(d, float(request.form["amount"]), note=request.form.get("note", ""))
            flash("Cash opening saved", "success")
        elif kind == "closing":
            system.close_cash(d, float(request.form["expected"]), float(request.form["actual"]), note=request.form.get("note", ""))
            system.refresh_daily_summary(d)
            flash("Cash closing saved", "success")
        return redirect(url_for("cash"))
    rows = db.execute("SELECT * FROM cash_openings ORDER BY date DESC LIMIT 100").fetchall()
    closes = db.execute("SELECT * FROM cash_closings ORDER BY date DESC LIMIT 100").fetchall()
    return render_template("cash.html", openings=rows, closings=closes, today=today.isoformat())


@app.route("/reports", methods=["GET", "POST"])
def reports():
    pnl_df = None
    monthly_df = None
    cash_df = None
    if request.method == "POST":
        rtype = request.form.get("type")
        if rtype == "pnl":
            pnl_df = PnLReport(request.form["start"], request.form.get("end")).profit_and_loss()
        elif rtype == "monthly":
            monthly_df = MonthlyExpenseReport().monthly(int(request.form["year"]))
        elif rtype == "cash":
            cash_df = CashReconReport().reconcile(request.form["date"])
    return render_template("reports.html", pnl=pnl_df, monthly=monthly_df, cash=cash_df, today=today.isoformat(), year=today.year)


@app.route("/export/<kind>")
def export(kind):
    if kind == "receipts":
        path = export_receipts()
    elif kind == "pnl":
        start = request.args.get("start", date.today().isoformat())
        end = request.args.get("end", date.today().isoformat())
        path = PnLReport(start, end).export()
    elif kind == "monthly":
        path = MonthlyExpenseReport().export(int(request.args.get("year", date.today().year)))
    elif kind == "cash":
        path = CashReconReport().export(request.args.get("date", date.today().isoformat()))
    else:
        flash("Unknown export", "error")
        return redirect(url_for("reports"))
    return send_file(str(path), as_attachment=True)


if __name__ == "__main__":
    print("Open: http://127.0.0.1:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
