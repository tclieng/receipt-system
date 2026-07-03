#!/usr/bin/env bash
# build.sh - Custom build for Render.com
# Installs Tesseract OCR system package + Python dependencies.
# No PyTorch / EasyOCR: keeps memory well under 512 MB on free tier.

set -e

echo "=== Installing Tesseract OCR (English + Malay + Simplified Chinese) ==="
apt-get update
apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-msa \
    tesseract-ocr-chi_sim
rm -rf /var/lib/apt/lists/*

echo "=== Installing Python dependencies ==="
pip install --no-cache-dir -r requirements.txt

echo "=== Verifying Tesseract installation ==="
tesseract --version

echo "=== Build complete ==="
