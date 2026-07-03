#!/usr/bin/env bash
# build.sh - Render.com build script for receipt-system.
#
# Installs Tesseract OCR + Python dependencies.
# Defensive: tries multiple apt configurations to work around
# Render build-cache mount issues on /var/lib/apt.

set -o errexit

echo "=== Build environment info ==="
echo "PWD: $(pwd)"
echo "User: $(whoami 2>/dev/null || echo unknown)"
echo "Python: $(python3 --version 2>&1 || echo not found)"
echo "lsb_release: $(lsb_release -a 2>&1 | head -3 || echo unknown)"
echo "Disk free: $(df -h /tmp 2>/dev/null | tail -1 || echo unknown)"

# Detect filesystem writability of common locations
for d in /tmp /var/lib/apt /var/lib/apt/lists; do
    if [ -d "$d" ]; then
        if [ -w "$d" ]; then
            echo "[ok]    writable: $d"
        else
            echo "[RO]    read-only: $d"
        fi
    else
        echo "[--]    missing:   $d"
    fi
done

echo ""
echo "=== Installing Tesseract OCR (eng + msa + chi_sim) ==="

# Use a writable location for apt state. Some Render build environments
# mount /var/lib/apt as read-only due to the build cache.
APT_STATE=/tmp/apt-state
rm -rf "$APT_STATE" 2>/dev/null || true
mkdir -p "$APT_STATE/lists/partial" "$APT_STATE/cache/archives/partial"

# Also symlink the expected partial dir into our writable state,
# in case apt hardcodes /var/lib/apt/lists/partial somewhere.
if [ -w /var/lib/apt/lists ] 2>/dev/null; then
    mkdir -p /var/lib/apt/lists/partial 2>/dev/null || true
fi

set +e
apt-get -o Dir::State="$APT_STATE" \
        -o Dir::State::Lists="$APT_STATE/lists" \
        -o Dir::Cache="$APT_STATE/cache" \
        -o Debug::pkgAcquire::Worker=1 \
        update 2>&1 | tail -30
APT_RC=$?
set -e

if [ $APT_RC -ne 0 ]; then
    echo ""
    echo "!!! apt-get update failed (rc=$APT_RC); retrying without -o flags in case /var/lib/apt is writable"
    apt-get update 2>&1 | tail -30 || true
fi

# Install tesseract + language packs
APT_INSTALL_OK=0
for try in 1 2 3; do
    echo "--- apt-get install attempt $try ---"
    set +e
    apt-get -o Dir::State="$APT_STATE" \
            -o Dir::State::Lists="$APT_STATE/lists" \
            -o Dir::Cache="$APT_STATE/cache" \
            install -y --no-install-recommends \
            tesseract-ocr \
            tesseract-ocr-eng \
            tesseract-ocr-msa \
            tesseract-ocr-chi_sim 2>&1 | tail -40
    if [ $? -eq 0 ]; then
        APT_INSTALL_OK=1
        break
    fi
    set -e
    sleep 2
done
set -e

if [ $APT_INSTALL_OK -ne 1 ]; then
    echo ""
    echo "!!! apt-get install failed after 3 attempts !!!"
    echo "Falling back: trying plain apt-get without custom -o flags..."
    apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-msa tesseract-ocr-chi_sim \
        || echo "FATAL: Could not install tesseract via apt"
fi

# Verify tesseract is installed
echo ""
echo "=== Verifying tesseract ==="
which tesseract || echo "tesseract not on PATH"
tesseract --version 2>&1 | head -3 || echo "tesseract --version failed"

# Clean up apt state to keep image small
rm -rf "$APT_STATE" 2>/dev/null || true

echo ""
echo "=== Installing Python dependencies ==="
pip install --no-cache-dir -r requirements.txt

echo ""
echo "=== Build complete ==="
