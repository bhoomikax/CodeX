from datetime import datetime

from pydantic import BaseModel, model_validator

from app.schemas.mistake import MistakeCategory


class SubmissionCreate(BaseModel):
    user_id: int
    problem_id: int
    code: str | None = None
    language: str
    status: str
    is_correct: bool
    mistake_category: MistakeCategory | None = None
    mistake_explanation: str | None = None
    mistake_correction: str | None = None

    @model_validator(mode="after")
    def validate_mistake_feedback(self):
        if self.is_correct and any(
            value is not None
            for value in (
                self.mistake_category,
                self.mistake_explanation,
                self.mistake_correction,
            )
        ):
            raise ValueError("Mistake feedback can only be attached to an incorrect submission")
        return self


class SubmissionResponse(BaseModel):
    id: int
    user_id: int
    problem_id: int
    code: str | None = None
    language: str
    status: str
    is_correct: bool
    submitted_at: datetime

    class Config:
        from_attributes = True