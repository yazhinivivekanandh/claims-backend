import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "claims.db"))
API_TOKEN = os.getenv("API_TOKEN", "")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
