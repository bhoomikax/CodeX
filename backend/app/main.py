import os

from fastapi import FastAPI
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.models import (
    User,
    Pattern,
    Problem,
    Submission,
    Mistake,
    PatternMastery,
    Note,
)

from app.routes import (
    users,
    patterns,
    problems,
    submissions,
    mistakes,
    mastery,
    recommendations,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CodeX API")

frontend_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(patterns.router)
app.include_router(problems.router)
app.include_router(submissions.router)
app.include_router(mistakes.router)
app.include_router(mastery.router)
app.include_router(recommendations.router)

@app.get("/")
def root():
    return {"message": "CodeX API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/health/db")
def database_health():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))

        return {
            "database": "connected",
            "result": result.scalar()
        }