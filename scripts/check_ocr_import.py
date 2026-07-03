#!/usr/bin/env python3
"""Diagnostic script: verify the rapidocr_onnxruntime import works.

Writes everything to /tmp/import_debug.log so we can see output even if
Python itself crashes (segfault, missing lib, OOM, etc.).
The Dockerfile will cat the log if exit code != 0.
"""
import os
import subprocess
import sys
import traceback

LOG = "/tmp/import_debug.log"


def log(msg=""):
    with open(LOG, "a") as f:
        f.write(str(msg) + "\n")
    # Mirror to stdout for good measure
    try:
        print(msg)
    except Exception:
        pass


def main():
    # Truncate
    try:
        open(LOG, "w").close()
    except Exception:
        pass

    log("=== check_ocr_import.py started ===")
    log(f"Python: {sys.version}")
    log(f"Platform: {sys.platform}")
    log(f"Executable: {sys.executable}")
    log(f"Working dir: {os.getcwd()}")
    log(f"LD_LIBRARY_PATH: {os.environ.get('LD_LIBRARY_PATH', '(unset)')}")
    log(f"PATH: {os.environ.get('PATH', '(unset)')[:200]}")

    # List relevant libs
    log("")
    log("--- lib search ---")
    for lib in ("libgomp", "libgl1", "libglib", "libgomp.so.1"):
        try:
            out = subprocess.run(
                ["find", "/usr/lib", "/lib", "-name", f"*{lib}*"],
                capture_output=True, text=True, timeout=10
            )
            if out.stdout.strip():
                log(f"{lib}: FOUND")
                for line in out.stdout.strip().splitlines()[:3]:
                    log(f"  {line}")
            else:
                log(f"{lib}: NOT FOUND")
        except Exception as e:
            log(f"  find for {lib} failed: {e}")

    log("")
    log("--- pip show ---")
    for pkg in ("rapidocr-onnxruntime", "onnxruntime", "opencv-python-headless", "numpy"):
        try:
            out = subprocess.run(
                ["pip", "show", pkg], capture_output=True, text=True, timeout=10
            )
            if out.returncode == 0:
                for line in out.stdout.splitlines():
                    if line.startswith(("Name:", "Version:", "Location:")):
                        log(line)
                log("")
            else:
                log(f"{pkg}: not installed")
        except Exception as e:
            log(f"pip show {pkg} failed: {e}")

    log("")
    log("--- attempting import ---")
    try:
        log("  step 1: import rapidocr_onnxruntime")
        import rapidocr_onnxruntime
        log(f"  step 1 OK: package at {rapidocr_onnxruntime.__file__}")
        log("  step 2: from rapidocr_onnxruntime import RapidOCR")
        from rapidocr_onnxruntime import RapidOCR
        log("  step 2 OK")
        log("=== ALL OK ===")
        return 0
    except Exception:
        log("=== IMPORT FAILED ===")
        log("Traceback:")
        log(traceback.format_exc())
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        # Catch-all: log and exit 1 so RUN sees a failure
        try:
            with open(LOG, "a") as f:
                f.write("\n=== UNCAUGHT EXCEPTION ===\n")
                f.write(traceback.format_exc())
        except Exception:
            pass
        sys.exit(1)
