from datetime import datetime

from pydantic import BaseModel, Field


class SubmissionCreate(BaseModel):
    user_id: int
    problem_id: int
    code: str = Field(min_length=1, max_length=50000)
    language: str


class SubmissionResponse(BaseModel):
    id: int
    user_id: int
    problem_id: int
    code: str | None = None
    language: str
    status: str
    is_correct: bool
    evaluation_details: dict | None = None
    mastery: dict | None = None
    mistake: dict | None = None
    recommendation: dict | None = None
    submitted_at: datetime

    class Config:
        from_attributes = True
