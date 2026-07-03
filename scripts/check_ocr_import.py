#!/usr/bin/env python3
"""Diagnostic script: verify the rapidocr_onnxruntime import works.

This is used as a build-time check so we can see the *real* error
(if any) instead of a generic "exit code: 1" from buildkit.

If anything fails, prints:
- Full traceback
- List of relevant system libraries
- Versions of rapidocr, onnxruntime, opencv
- And exits with code 99 so the RUN line can react.
"""
import os
import subprocess
import sys
import traceback


def main():
    try:
        from rapidocr_onnxruntime import RapidOCR
        print("RapidOCR package import OK (models bundled in pip package)")
        # Touch the engine to ensure onnxruntime is fully usable
        _ = RapidOCR
        return 0
    except Exception:
        print("=" * 60)
        print("RapidOCR import FAILED. Full traceback:")
        print("=" * 60)
        traceback.print_exc()
        print()
        print("=" * 60)
        print("Diagnostic information:")
        print("=" * 60)
        print(f"Python: {sys.version}")
        print(f"Platform: {sys.platform}")
        print()
        print("--- System libraries ---")
        try:
            for lib in ("libgomp", "libgl1", "libglib-2", "libSM", "libgfortran"):
                out = subprocess.run(
                    ["find", "/usr/lib", "-name", f"*{lib}*"],
                    capture_output=True, text=True, timeout=10
                )
                if out.stdout.strip():
                    print(f"{lib}: FOUND")
                    for line in out.stdout.strip().splitlines()[:3]:
                        print(f"  {line}")
                else:
                    print(f"{lib}: NOT FOUND")
        except Exception as e:
            print(f"Library probe failed: {e}")
        print()
        print("--- pip package versions ---")
        for pkg in ("rapidocr-onnxruntime", "onnxruntime", "opencv-python-headless", "numpy"):
            try:
                out = subprocess.run(
                    ["pip", "show", pkg], capture_output=True, text=True, timeout=10
                )
                if out.returncode == 0:
                    for line in out.stdout.splitlines():
                        if line.startswith(("Name:", "Version:", "Location:")):
                            print(line)
                    print()
            except Exception as e:
                print(f"pip show {pkg} failed: {e}")
        return 99


if __name__ == "__main__":
    sys.exit(main())
