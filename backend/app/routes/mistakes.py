from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.mistake import Mistake
from app.models.submission import Submission
from app.schemas.mistake import MistakeCategory, MistakeCreate, MistakeResponse
from app.services.mistake import create_mistake as save_mistake

router = APIRouter(
    prefix="/mistakes",
    tags=["Mistakes"]
)


@router.post("/", response_model=MistakeResponse)
def create_mistake(
    submission_id: int,
    category: MistakeCategory,
    explanation: str | None = None,
    correction: str | None = None,
    db: Session = Depends(get_db)
):
    submission = (
        db.query(Submission)
        .filter(Submission.id == submission_id)
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.is_correct:
        raise HTTPException(
            status_code=400,
            detail="Mistakes can only be recorded for incorrect submissions",
        )

    existing_mistake = (
        db.query(Mistake)
        .filter(Mistake.submission_id == submission_id)
        .first()
    )
    if existing_mistake:
        raise HTTPException(
            status_code=409,
            detail="A mistake is already recorded for this submission",
        )

    try:
        mistake_data = MistakeCreate(
            submission_id=submission_id,
            category=category,
            explanation=explanation,
            correction=correction,
        )
        mistake = save_mistake(
            db=db,
            submission_id=mistake_data.submission_id,
            category=mistake_data.category,
            explanation=mistake_data.explanation,
            correction=mistake_data.correction,
        )
        db.commit()
        db.refresh(mistake)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to save mistake",
        ) from exc

    return mistake


@router.get("/", response_model=list[MistakeResponse])
def get_mistakes(
    user_id: int | None = Query(default=None, gt=0, description="Only return this learner's mistakes"),
    db: Session = Depends(get_db),
):
    query = db.query(Mistake)
    if user_id is not None:
        query = query.join(Submission, Submission.id == Mistake.submission_id).filter(Submission.user_id == user_id)
    return query.order_by(Mistake.id).all()


@router.get(
    "/submission/{submission_id}",
    response_model=list[MistakeResponse],
)
def get_submission_mistakes(
    submission_id: int,
    db: Session = Depends(get_db),
):
    submission = (
        db.query(Submission)
        .filter(Submission.id == submission_id)
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    return (
        db.query(Mistake)
        .filter(Mistake.submission_id == submission_id)
        .order_by(Mistake.id)
        .all()
    )


@router.get("/{mistake_id}", response_model=MistakeResponse)
def get_mistake(
    mistake_id: int,
    db: Session = Depends(get_db)
):
    mistake = (
        db.query(Mistake)
        .filter(Mistake.id == mistake_id)
        .first()
    )

    if not mistake:
        raise HTTPException(
            status_code=404,
            detail="Mistake not found"
        )

    return mistake