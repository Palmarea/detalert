"""Entrada de Vercel: expone la app FastAPI (ASGI) de src/aml/api/main.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aml.api.main import app  # noqa: E402,F401
