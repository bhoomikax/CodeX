import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# backend/.env, located from this file so the working directory never matters.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_backend_env(path=ENV_FILE):
    """Load settings from the .env file. Variables already present in the
    process environment (e.g. set in the shell) take precedence. The file is
    read once at startup; restart the backend after editing it."""
    return load_dotenv(path, override=False)


# Unit tests set CODEX_SKIP_DOTENV=1 so they never see real keys or databases.
if os.getenv("CODEX_SKIP_DOTENV") != "1":
    load_backend_env()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

import app.models