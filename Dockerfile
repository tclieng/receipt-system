# syntax=docker/dockerfile:1.6
# Pure-Python Dockerfile for receipt-system
# Uses RapidOCR (ONNX runtime) - no system packages, no apt-get needed
# Render Docker build doesn't have apt-get network access, so we go pure-pip.

FROM python:3.11-slim

ARG CACHEBUST=2026-07-03-r5

WORKDIR /app

# Just Python deps - everything is pip-installable now
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Verify the package imports cleanly. Surface the actual error so we can
# diagnose. (Models are bundled inside the pip package, no CDN download.)
RUN python -c "import sys; import traceback
try:
    from rapidocr_onnxruntime import RapidOCR
    print('RapidOCR package import OK')
except Exception:
    traceback.print_exc()
    sys.exit(99)" || (echo '=== EXIT CODE:' $? '===' && echo '=== Listing /usr/lib for libgomp/libgl ===' && ls /usr/lib/x86_64-linux-gnu/ 2>&1 | grep -E 'libgomp|libgl|libgomp1' || true && echo '=== Python info ===' && python -V && pip show rapidocr-onnxruntime onnxruntime opencv-python-headless 2>&1 | head -20 && exit 1)

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
