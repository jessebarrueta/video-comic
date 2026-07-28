#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import sys
if sys.version_info >= (3, 14):
    raise SystemExit(
        "This project currently supports Python 3.11–3.13. "
        "Recreate .venv with Python 3.12 or 3.13."
    )
PY

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
