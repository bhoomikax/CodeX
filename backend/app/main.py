from fastapi import FastAPI
from sqlalchemy import text

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