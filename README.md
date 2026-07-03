# Receipt Processing System

Local document processing system for bills, cash reconciliation, profit & loss reporting, and Excel exports.

## Features

- Receipt/invoice scanning with EasyOCR
- SQLite database: receipts, suppliers, expenses, sales, cash open/close, staff, daily summary
- P&L reporting
- Monthly expense analysis
- Daily cash reconciliation
- Excel export
- Flask web UI
- CLI for headless/desktop use

## Quick start

```bash
git clone https://github.com/tclieng/receipt-system.git
cd receipt-system
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python scripts/app.py db
python scripts/app.py opening 2026-07-03 500.0
python scripts/app.py sale 2026-07-03 200.0 --payment cash
python scripts/app.py expense 2026-07-03 120.0 --category utilities
python scripts/app.py closing 2026-07-03 1020.0 1040.0
python scripts/app.py pnl --start 2026-07-01
python scripts/app.py monthly 2026
python scripts/app.py receipts
python scripts/app.py cash 2026-07-03
```

Scan a receipt image:
```bash
python scripts/app.py scan "C:\path\to\receipt.jpg"
```

Start Flask web UI:
```bash
cd web
python app.py
# open http://127.0.0.1:5000
```

## Excel exports

Exports are saved under:
```text
C:\Users\MK-User\receipt-system\data\exports\
```
