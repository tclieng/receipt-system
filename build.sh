#!/usr/bin/env bash
# build.sh - Render.com build script for receipt-system.
#
# Installs Tesseract OCR + Python dependencies.
#
# Workaround: Render's build cache mounts /var/lib/apt as read-only,
# causing "List directory /var/lib/apt/lists/partial is missing" errors.
# We redirect all apt state to /tmp (writable) via -o Dir::State=...

set -o errexit

echo "=== Installing Tesseract OCR (eng + msa + chi_sim) ==="
APT_STATE=/tmp/apt-state
mkdir -p "$APT_STATE/lists/partial" "$APT_STATE/cache/archives/partial"

apt-get -o Dir::State="$APT_STATE" \
        -o Dir::State::Lists="$APT_STATE/lists" \
        -o Dir::Cache="$APT_STATE/cache" \
        update

apt-get -o Dir::State="$APT_STATE" \
        -o Dir::State::Lists="$APT_STATE/lists" \
        -o Dir::Cache="$APT_STATE/cache" \
        install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-msa \
        tesseract-ocr-chi_sim

# Verify tesseract works
tesseract --version

# Clean up apt state (keeps the deployed image small)
rm -rf "$APT_STATE"

echo "=== Installing Python dependencies ==="
pip install --no-cache-dir -r requirements.txt

echo "=== Build complete ==="
