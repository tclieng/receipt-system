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

# Verify the OCR engine loads at build time
RUN python -c "from rapidocr_onnxruntime import RapidOCR; print('RapidOCR build check OK')"

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
