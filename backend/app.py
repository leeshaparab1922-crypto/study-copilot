"""FastAPI app entrypoint for the StudyPlanFlow HTTP layer.

Usage:
    uv run uvicorn backend.app:app --reload
"""

import sys

if sys.stdout.encoding.lower() != "utf-8":
    # Windows cp1252 console can't print CrewAI's UTF-8 log output (box-drawing chars, etc.)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from backend.routes import router

app = FastAPI(title="Adaptive Study Planning System")
app.include_router(router)
