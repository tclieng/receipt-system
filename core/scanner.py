"""
Receipt scanner using RapidOCR (ONNX Runtime backend).

Pure-Python replacement for Tesseract that does NOT need any system packages.
Works on Render's Docker build without any apt-get install step.

Memory: ~100 MB total (well under Render's 512 MB free tier)
Speed: ~1-2s per image
Languages: English, Chinese (Simplified), Bahasa Malaysia (Latin only)

Usage:
    python -m core.scanner path/to/image.jpg
    scanner.scan(image_path)
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

from .schema import get_connection, init_db


class ReceiptScanner:
    """Wrapper around RapidOCR with the same .extract() / .save_receipt() API
    as the Tesseract version, so the rest of the app doesn't change."""

    def __init__(self):
        # Lazy import so missing ONNX binaries surface as a clear error
        # only when the scanner is actually used (not at import time).
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()
        print("RapidOCR (ONNX) engine ready")

    def preprocess(self, image_path: str):
        """Read + downscale + grayscale + denoise. RapidOCR works on the
        original BGR image, but downscaling first keeps memory low."""
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Image not found: {image_path}")
        h, w = img.shape[:2]
        max_dim = 1600
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        return img

    def extract(self, image_path: str) -> dict:
        img = self.preprocess(image_path)

        # RapidOCR returns (None, [(box, text, confidence), ...], elapsed)
        result = self._engine(img)
        if not result or result[1] is None:
            raise RuntimeError("RapidOCR returned no text for the image")

        # Combine detected text lines into a single string, ordered top-to-bottom.
        lines_with_pos = []
        for box, text, conf in result[1]:
            if not text or not text.strip():
                continue
            # Top y-coordinate (box is 4 corners).
            y_top = min(p[1] for p in box)
            lines_with_pos.append((y_top, text.strip()))

        # Sort by vertical position so multi-line layout reads naturally.
        lines_with_pos.sort(key=lambda t: t[0])
        lines = [text for _, text in lines_with_pos]
        text_clean = "\n".join(lines)

        parsed = {
            "ocr_text": text_clean,
            "date": self._parse_date(text_clean),
            "total_amount": self._parse_total(text_clean),
            "tax_amount": self._parse_tax(text_clean),
            "payment_method": self._parse_payment(text_clean),
            "supplier": self._parse_supplier(text_clean),
            "items": self._parse_items(lines),
        }
        return parsed

    # ---- Parsing helpers (kept identical to the Tesseract version) ----

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
                r"(?:Total|Amount|Grand Total|Payable|Balance|Ringgit)[:\s]+[^\d]*([\d,]+\.?\d*)",
                r"RM\s*([\d,]+\.?\d*)",
                r"MYR\s*([\d,]+\.?\d*)",
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
            text,
            [
                r"GST[:\s]+([\d,]+\.?\d*)",
                r"SST[:\s]+([\d,]+\.?\d*)",
                r"Tax[:\s]+([\d,]+\.?\d*)",
                r"([\d,]+\.?\d*)\s*%\s*SST",
            ],
        )
        if raw:
            try:
                return float(raw.replace(",", ""))
            except ValueError:
                return 0.0
        return 0.0

    def _parse_payment(self, text: str) -> Optional[str]:
        up = text.upper()
        if any(k in up for k in ["CASH", "TUNAI"]):
            return "cash"
        if any(k in up for k in ["CARD", "CREDIT", "DEBIT", "VISA", "MASTERCARD", "MYDEBIT"]):
            return "card"
        if any(k in up for k in ["QR", "TOUCH", "GO PAY", "GRABPAY", "SHOPEEPAY", "DUITNOW"]):
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
            if any(k in line.upper() for k in [
                "TOTAL", "AMOUNT", "PAY", "CASH", "CARD", "TAX", "SST",
                "GST", "DATE", "TIME", "REF", "NO", "BILL", "INVOICE",
                "THANK", "TERIMA", "KASIH",
            ]):
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
