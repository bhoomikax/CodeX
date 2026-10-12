from datetime import datetime

from pydantic import BaseModel


class PatternProgressResponse(BaseModel):
    pattern_id: int
    pattern_name: str
    mastery_score: float
    confidence_score: float
    retention_score: float
    total_attempts: int
    correct_attempts: int
    accuracy_percentage: float
    consecutive_correct: int


class RecentSubmissionResponse(BaseModel):
    id: int
    problem_id: int
    problem_title: str
    pattern_id: int
    pattern_name: str
    language: str
    status: str
    is_correct: bool
    submitted_at: datetime | None


class LearnerProgressResponse(BaseModel):
    user_id: int
    total_attempts: int
    correct_attempts: int
    accuracy_percentage: float
    patterns: list[PatternProgressResponse]
    strongest_pattern: PatternProgressResponse | None
    weakest_pattern: PatternProgressResponse | None
    recent_submissions: list[RecentSubmissionResponse]
