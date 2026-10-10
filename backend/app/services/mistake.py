from sqlalchemy.orm import Session

from app.models.mistake import Mistake
from app.schemas.mistake import MistakeCategory


def create_mistake(
    db: Session,
    submission_id: int,
    category: MistakeCategory,
    explanation: str | None = None,
    correction: str | None = None,
) -> Mistake:
    mistake = Mistake(
        submission_id=submission_id,
        category=category,
        explanation=explanation,
        correction=correction,
    )
    db.add(mistake)
    db.flush()
    return mistake