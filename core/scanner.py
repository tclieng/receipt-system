"""
Receipt scanner using EasyOCR.
Usage:
    python -m core.scanner path/to/image.jpg
    scanner.scan(image_path)
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import easyocr
import numpy as np

from .schema import get_connection, init_db


class ReceiptScanner:
    def __init__(self):
        print("Loading EasyOCR model (first run downloads langdetect + English model)...")
        self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    def preprocess(self, image_path: str):
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Image not found: {image_path}")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        den = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
        return den, img

    def extract(self, image_path: str) -> dict:
        den, img = self.preprocess(image_path)
        results = self.reader.readtext(den, detail=0, paragraph=True)
        lines = [line.strip() for line in results if line.strip()]
        text = "\n".join(lines)
        parsed = {
            "ocr_text": text,
            "date": self._parse_date(text),
            "total_amount": self._parse_total(text),
            "tax_amount": self._parse_tax(text),
            "payment_method": self._parse_payment(text),
            "supplier": self._parse_supplier(text),
            "items": self._parse_items(lines),
        }
        return parsed

    def _first_match(self, text: str, patterns: list[str]) -> Optional[str]:
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    def _parse_date(self, text: str) -> Optional[str]:
        raw = self._first_match(
            text,
            [
                r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
                r"Date[:\s]+(\d{1,2}[-]\d{1,2}[-]\d{2,4})",
                r"(\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{2,4})",
            ],
        )
        if not raw:
            return None
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        return raw

    def _parse_total(self, text: str) -> Optional[float]:
        raw = self._first_match(
            text,
            [
                r"(?:Total|Amount|Grand Total|Payable|Balance)[:\s]+[^\d]*([\d,]+\.?\d*)",
                r"RM\s*([\d,]+\.?\d*)",
                r"(\d+\.\d{2})\s*$",
            ],
        )
        if raw:
            try:
                return float(raw.replace(",", ""))
            except ValueError:
                return None
        return None

    def _parse_tax(self, text: str) -> float:
        raw = self._first_match(
            text, [r"GST[:\s]+([\d,]+\.?\d*)", r"SST[:\s]+([\d,]+\.?\d*)", r"Tax[:\s]+([\d,]+\.?\d*)", r"([\d,]+\.?\d*)\s*%\s*SST"]
        )
        if raw:
            try:
                return float(raw.replace(",", ""))
            except ValueError:
                return 0.0
        return 0.0

    def _parse_payment(self, text: str) -> Optional[str]:
        up = text.upper()
        if any(k in up for k in ["CASH"]):
            return "cash"
        if any(k in up for k in ["CARD", "CREDIT"]):
            return "card"
        if any(k in up for k in ["QR", "TOUCH", "GO PAY", "GRABPAY"]):
            return "qr"
        return None

    def _parse_supplier(self, text: str) -> Optional[str]:
        candidates = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if any(d.isdigit() for d in line):
                continue
            if any(k in line.upper() for k in ["TOTAL", "AMOUNT", "PAY", "CASH", "CARD", "TAX", "SST", "DATE", "TIME", "REF", "NO"]):
                continue
            if 3 <= len(line) <= 60:
                candidates.append(line)
        return candidates[0] if candidates else None

    def _parse_items(self, lines: list[str]) -> list[dict]:
        items = []
        for line in lines:
            if not any(ch.isdigit() for ch in line):
                continue
            m = re.search(r"(.+?)\s+(\d+(?:\.\d+)?)\s*x\s*([\d,]+\.?\d*)\s+([\d,]+\.?\d*)", line)
            if m:
                items.append({
                    "name": m.group(1).strip(),
                    "quantity": float(m.group(2)),
                    "unit_price": float(m.group(3).replace(",", "")),
                    "total_price": float(m.group(4).replace(",", "")),
                })
                continue
            m = re.search(r"(.+?)\s+([\d,]+\.?\d*)\s*$", line)
            if m:
                items.append({
                    "name": m.group(1).strip(),
                    "quantity": 1.0,
                    "unit_price": None,
                    "total_price": float(m.group(2).replace(",", "")),
                })
        return items

    def save_receipt(self, image_path: str, parsed: dict) -> int:
        init_db()
        file_path = str(Path(image_path).resolve())
        with get_connection() as conn:
            cur = conn.cursor()
            supplier = parsed.get("supplier")
            supplier_id = None
            if supplier:
                cur.execute("INSERT OR IGNORE INTO suppliers(name,category) VALUES(?,?)", (supplier, "bills"))
                conn.commit()
                cur.execute("SELECT id FROM suppliers WHERE name=?", (supplier,))
                supplier_id = cur.fetchone()["id"]

            cur.execute(
                """
                INSERT INTO receipts(file_name,file_path,date,supplier_id,total_amount,tax_amount,payment_method,ocr_text,status)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    Path(image_path).name,
                    file_path,
                    parsed.get("date"),
                    supplier_id,
                    parsed.get("total_amount"),
                    parsed.get("tax_amount") or 0,
                    parsed.get("payment_method"),
                    parsed.get("ocr_text"),
                    "processed",
                ),
            )
            receipt_id = cur.lastrowid

            item_rows = []
            for item in parsed.get("items", []):
                item_rows.append(
                    (
                        receipt_id,
                        item.get("name"),
                        item.get("quantity", 1),
                        item.get("unit_price"),
                        item.get("total_price"),
                        "other",
                    )
                )
            if item_rows:
                cur.executemany(
                    """
                    INSERT INTO receipt_items(receipt_id,item_name,quantity,unit_price,total_price,category)
                    VALUES(?,?,?,?,?,?)
                    """,
                    item_rows,
                )
            conn.commit()
            return receipt_id


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m core.scanner <image_path>")
        sys.exit(1)
    scanner = ReceiptScanner()
    parsed = scanner.extract(sys.argv[1])
    receipt_id = scanner.save_receipt(sys.argv[1], parsed)
    print(f"Saved receipt id={receipt_id}")
    print(parsed)
