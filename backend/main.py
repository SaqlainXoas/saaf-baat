from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_BACKEND_DIR / "src"))
load_dotenv(_BACKEND_DIR / ".env")

from src.api.app import create_app  # noqa: E402

app = create_app()

