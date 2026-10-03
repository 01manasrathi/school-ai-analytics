import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'ib_options.db').as_posix()}")
SECRET_KEY = os.getenv("SECRET_KEY", "local-dev-secret-change-me")
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "12"))
PBKDF2_ITERATIONS = int(os.getenv("PBKDF2_ITERATIONS", "200000"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
