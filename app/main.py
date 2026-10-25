"""uvicorn entry point: `uvicorn app.main:app --host 0.0.0.0 --port 8000`."""
from __future__ import annotations

import logging

from .config import load_settings
from .web import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = load_settings()
app = create_app(settings, start_scheduler=True)
