from typing import Literal

from pydantic import BaseModel


MistakeCategory = Literal[
    "logic_error",
    "syntax_error",
    "edge_case",
    "inefficient_solution",
    "unknown",
]


class MistakeCreate(BaseModel):
    submission_id: int
    category: MistakeCategory = "unknown"
    explanation: str | None = None
    correction: str | None = None


class MistakeResponse(BaseModel):
    id: int
    submission_id: int
    category: MistakeCategory
    explanation: str | None = None
    correction: str | None = None

    class Config:
        from_attributes = True