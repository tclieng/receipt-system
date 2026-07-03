# syntax=docker/dockerfile:1.6
# Pure-Python Dockerfile for receipt-system
# Uses RapidOCR (ONNX runtime) - no apt-get needed in the build.
# Base image: python:3.11-bookworm (full Debian) - bundles libgomp1, libgl1,
# libglib2.0-0 etc. so onnxruntime and opencv-python work out of the box.
# python:3.11-slim was failing because those system libs are missing and
# we can't apt-get install them (Render's buildkit blocks Debian mirrors).

FROM python:3.11-bookworm

ARG CACHEBUST=2026-07-03-r7-diagnostics

WORKDIR /app

# Just Python deps - everything is pip-installable now
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Verify the package imports cleanly. Diagnostic script surfaces the real
# error (full traceback + lib probe + pip versions) instead of a bare
# "exit code: 1". Models are bundled inside the pip package, no CDN needed.
COPY scripts/check_ocr_import.py /tmp/check_ocr_import.py
RUN python /tmp/check_ocr_import.py || { echo "=== BUILD FAILED: rapidocr import check ==="; exit 1; }

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
