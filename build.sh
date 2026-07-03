#!/usr/bin/env bash
# build.sh - Custom build for Render.com
# Installs PyTorch CPU-only first (faster, smaller), then everything else.
# PyTorch CPU-only is ~200MB vs ~700MB for GPU build, fits in Render's
# build/cache limits better.

set -e

echo "=== Installing PyTorch CPU-only (faster, smaller) ==="
pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

echo "=== Installing remaining dependencies ==="
pip install --no-cache-dir -r requirements.txt

echo "=== Pre-downloading EasyOCR English model (avoids timeout on first scan) ==="
python -c "import easyocr; reader = easyocr.Reader(['en'], gpu=False, verbose=False); print('EasyOCR model loaded OK')" || {
    echo "WARNING: EasyOCR model pre-download failed, will retry at runtime"
}

echo "=== Build complete ==="
