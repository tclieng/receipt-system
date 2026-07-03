#!/usr/bin/env bash
# build.sh - Custom build for Render.com
# Installs PyTorch CPU-only first, then all other dependencies

set -e

echo "=== Installing PyTorch CPU-only (faster, smaller) ==="
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

echo "=== Installing remaining dependencies ==="
pip install -r requirements.txt

echo "=== Pre-downloading EasyOCR model (avoids first-request timeout) ==="
python -c "import easyocr; easyocr.Reader(['en'], gpu=False, verbose=False)" || echo "EasyOCR model download failed at build time, will retry on first request"

echo "=== Build complete ==="
