#!/usr/bin/env bash
# build.sh - Custom build for Render.com
# Installs PyTorch CPU-only first, then all other dependencies

set -e

echo "=== Installing PyTorch CPU-only (faster, smaller) ==="
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

echo "=== Installing remaining dependencies ==="
pip install -r requirements.txt

echo "=== Build complete ==="
