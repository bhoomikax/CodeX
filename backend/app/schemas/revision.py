from datetime import datetime

from pydantic import BaseModel


class RevisionRecommendationResponse(BaseModel):
    pattern_id: int
    pattern_name: str
    mastery_score: float
    due_at: datetime
    problem_id: int
    problem_title: str
    difficulty: str
    reason: str
    priority: float
