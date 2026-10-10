from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.submission import Submission
from app.models.problem import Problem
from app.schemas.submission import SubmissionCreate, SubmissionResponse
from app.services.mistake import create_mistake
from app.services.mastery import update_mastery

router = APIRouter(
    prefix="/submissions",
    tags=["Submissions"]
)


@router.post("/", response_model=SubmissionResponse)
def create_submission(
    submission: SubmissionCreate,
    db: Session = Depends(get_db)
):
    problem = (
        db.query(Problem)
        .filter(Problem.id == submission.problem_id)
        .first()
    )

    if not problem:
        raise HTTPException(
            status_code=404,
            detail="Problem not found"
        )

    try:
        new_submission = Submission(
            user_id=submission.user_id,
            problem_id=submission.problem_id,
            code=submission.code,
            language=submission.language,
            status=submission.status,
            is_correct=submission.is_correct,
        )
        db.add(new_submission)
        db.flush()

        if not submission.is_correct:
            create_mistake(
                db=db,
                submission_id=new_submission.id,
                category=submission.mistake_category or "unknown",
                explanation=(
                    submission.mistake_explanation
                    or "The submission was marked incorrect; the specific cause was not automatically diagnosed."
                ),
                correction=(
                    submission.mistake_correction
                    or "Review the problem requirements and test the solution against edge cases."
                ),
            )

        update_mastery(
            db=db,
            user_id=submission.user_id,
            pattern_id=problem.pattern_id,
            is_correct=submission.is_correct,
        )
        db.commit()
        db.refresh(new_submission)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to save submission and associated records",
        ) from exc

    return new_submission


@router.get("/", response_model=list[SubmissionResponse])
def get_submissions(db: Session = Depends(get_db)):
    return db.query(Submission).all()


@router.get("/{submission_id}", response_model=SubmissionResponse)
def get_submission(
    submission_id: int,
    db: Session = Depends(get_db)
):
    submission = (
        db.query(Submission)
        .filter(Submission.id == submission_id)
        .first()
    )

    if not submission:
        raise HTTPException(
            status_code=404,
            detail="Submission not found"
        )

    return submission