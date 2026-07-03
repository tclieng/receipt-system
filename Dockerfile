# syntax=docker/dockerfile:1.6
# receipt-system Dockerfile - onnxruntime-friendly variant
#
# Strategy: download libgomp1 (and friends) as a .deb file via curl
# (pip works in Render's build, so curl should too), then extract it
# with dpkg-deb -x into /. This sidesteps the broken apt-get.

FROM python:3.11-bookworm

ARG CACHEBUST=2026-07-03-r8-manual-libgomp

WORKDIR /app

# ----------------------------------------------------------------
# 1) Install system libraries that onnxruntime / opencv need
# ----------------------------------------------------------------
# Try several Debian mirror URLs for libgomp1, libgl1, libglib2.0-0.
# This is done WITHOUT apt-get update (which hangs on Render's build).
# dpkg-deb -x extracts the contents into the image filesystem.
#
# If curl is reachable, we get the libs we need. If not, the build
# will fail at the rapidocr import and we'll see exactly what's missing.
RUN set -e; \
    mkdir -p /opt/sysroot && cd /opt/sysroot && \
    echo "=== Trying to download libgomp1 .deb ===" && \
    for url in \
        "http://deb.debian.org/debian/pool/main/g/gcc-12/libgomp1_12.2.0-14+deb12u1_amd64.deb" \
        "http://ftp.debian.org/debian/pool/main/g/gcc-12/libgomp1_12.2.0-14+deb12u1_amd64.deb" \
        "http://archive.debian.org/debian/pool/main/g/gcc-12/libgomp1_12.2.0-14+deb12u1_amd64.deb" \
        "http://security.debian.org/debian-security/pool/updates/main/g/gcc-12/libgomp1_12.2.0-14+deb12u1_amd64.deb" \
    ; do \
        echo "Trying: $url"; \
        if curl -sSL --fail --max-time 30 -o libgomp1.deb "$url"; then \
            echo "  -> downloaded $(wc -c < libgomp1.deb) bytes"; \
            dpkg-deb -x libgomp1.deb / && echo "  -> extracted OK" && break; \
        else \
            echo "  -> FAILED"; \
        ; \
        rm -f libgomp1.deb; \
    done; \
    echo "=== Verifying libgomp.so.1 is on disk ===" && \
    find / -name 'libgomp.so*' 2>/dev/null || true

# ----------------------------------------------------------------
# 2) Install Python deps
# ----------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------------------------------
# 3) Copy app and run the diagnostic
# ----------------------------------------------------------------
COPY . .
COPY scripts/check_ocr_import.py /tmp/check_ocr_import.py
RUN python /tmp/check_ocr_import.py && echo "=== CHECK PASSED ===" || { echo "=== CHECK FAILED, log follows ==="; cat /tmp/import_debug.log 2>&1 || echo "(no log file written)"; exit 1; }

# Mark this image as the RapidOCR build (for runtime diagnostic)
RUN echo "rapidocr-build-${CACHEBUST}" > /opt/ocr-marker.txt

ENV PORT=8000
EXPOSE 8000

CMD gunicorn web.app:app \
    --bind 0.0.0.0:$PORT \
    --worker-class gthread \
    --workers 1 \
    --threads 2 \
    --timeout 300 \
    --graceful-timeout 60 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile -
