"""
Receipt scanner using Tesseract OCR.

Lightweight replacement for EasyOCR: ~80 MB total memory vs ~700 MB,
runs ~10x faster, and fits comfortably on Render's 512 MB free tier.

Usage:
    python -m core.scanner path/to/image.jpg
    scanner.scan(image_path)
"""
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import pytesseract

from .schema import get_connection, init_db


# Known tesseract binary locations on Debian/Render (tried in order).
_TESSERACT_PATHS = [
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/usr/local/sbin/tesseract",
    "/bin/tesseract",
]


class ReceiptScanner:
    # English + Bahasa Malaysia + Simplified Chinese
    LANGUAGES = "eng+msa+chi_sim"

    def __init__(self):
        # Try the default pytesseract lookup first.
        try:
            version = pytesseract.get_tesseract_version()
            print(f"Tesseract OCR loaded: v{version}")
            return
        except pytesseract.TesseractNotFoundError:
            pass

        # pytesseract couldn't find it via PATH. Try our own search.
        # 0. TESSERACT_PATH env var (set by our Dockerfile)
        env_hint = os.environ.get("TESSERACT_PATH")
        binary = None
        if env_hint and os.path.isfile(env_hint) and os.access(env_hint, os.X_OK):
            binary = env_hint

        # 1. shutil.which (respects current PATH)
        if not binary:
            binary = shutil.which("tesseract")

        # 2. Common Debian/Render locations
        if not binary:
            for path in _TESSERACT_PATHS:
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    binary = path
                    break

        if binary:
            # Found it — point pytesseract directly at it.
            pytesseract.tesseract_cmd = binary
            version = pytesseract.get_tesseract_version()
            print(f"Tesseract OCR loaded via fallback path ({binary}): v{version}")
            return

        # Give up with a helpful, diagnostic error.
        tried = ["PATH"] + _TESSERACT_PATHS
        diag_lines = [f"Tesseract binary not found. Tried: {', '.join(tried)}"]
        # Diagnostics: what's actually on the system
        diag_lines.append(f"PATH env: {os.environ.get('PATH', '(unset)')}")
        diag_lines.append(f"TESSERACT_PATH env: {env_hint or '(unset)'}")
        diag_lines.append(f"Platform: {sys.platform}")
        # Check the build-time marker (proves the Dockerfile install ran)
        marker = Path("/opt/tesseract-marker.txt")
        if marker.exists():
            diag_lines.append(f"Build marker EXISTS: {marker.read_text().strip()!r} (this image was built with tesseract)")
        else:
            diag_lines.append("Build marker MISSING at /opt/tesseract-marker.txt (this image was NOT built from current Dockerfile)")
        # Look anywhere on disk (bounded)
        try:
            import subprocess
            find_result = subprocess.run(
                ["find", "/", "-name", "tesseract", "-type", "f", "-executable"],
                capture_output=True, text=True, timeout=10
            )
            if find_result.stdout.strip():
                diag_lines.append(f"Found tesseract binaries: {find_result.stdout.strip()}")
            else:
                diag_lines.append("No tesseract binary found anywhere under /")
        except Exception as fe:
            diag_lines.append(f"find failed: {fe}")
        # Check dpkg
        try:
            import subprocess
            dpkg_result = subprocess.run(
                ["dpkg", "-l", "tesseract-ocr"],
                capture_output=True, text=True, timeout=5
            )
            diag_lines.append(f"dpkg -l tesseract-ocr: {dpkg_result.stdout.strip() or '(no output)'}")
        except Exception:
            diag_lines.append("dpkg not available (probably not in this image)")
        diag_lines.append(
            "Install with: apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-msa tesseract-ocr-chi_sim"
        )
        raise RuntimeError("\n".join(diag_lines))

    def preprocess(self, image_path: str):
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Downscale very large images (memory + speed). 1600 px on the long side
        # is plenty for receipt OCR and dramatically reduces per-request memory.
        h, w = img.shape[:2]
        max_dim = 1600
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Adaptive thresholding works well for receipts with mixed lighting.
        # Fall back to Otsu if image is too small for the kernel.
        if min(gray.shape) >= 31:
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
            )
        else:
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Light denoise
        den = cv2.fastNlMeansDenoising(binary, h=8, templateWindowSize=7, searchWindowSize=21)
        return den, img

    def extract(self, image_path: str) -> dict:
        binary, img = self.preprocess(image_path)

        # PSM 6 = Assume a single uniform block of text (good for receipts).
        # OEM 3 = Default LSTM engine.
        config = "--oem 3 --psm 6"
        text = pytesseract.image_to_string(binary, lang=self.LANGUAGES, config=config)

        lines = [line.strip() for line in text.splitlines() if line.strip()]
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
