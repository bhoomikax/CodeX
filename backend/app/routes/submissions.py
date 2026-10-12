from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Problem, Submission, User
from app.schemas.submission import SubmissionCreate, SubmissionResponse
from app.services.evaluator import EvaluationError, EvaluationUnavailable, evaluate_submission
from app.services.feedback import generate_feedback
from app.services.mastery import update_mastery
from app.services.mistake import create_mistake
from app.services.recommendation import recommend_problem

router = APIRouter(prefix="/submissions", tags=["Submissions"])


@router.post("/", response_model=SubmissionResponse)
def create_submission(submission: SubmissionCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == submission.user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    problem = db.query(Problem).filter(Problem.id == submission.problem_id).first()
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")

    try:
        evaluation = evaluate_submission(problem, submission.code, submission.language)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EvaluationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EvaluationError as exc:
        raise HTTPException(status_code=502, detail=f"Evaluation Error: {exc}") from exc

    try:
        feedback = generate_feedback(problem, submission.code, submission.language, evaluation)
        new_submission = Submission(
            user_id=submission.user_id,
            problem_id=submission.problem_id,
            code=submission.code,
            language=submission.language.lower(),
            status=evaluation.status,
            is_correct=evaluation.is_correct,
            evaluation_details={**evaluation.as_dict(), "feedback": feedback},
        )
        db.add(new_submission)
        db.flush()

        mastery = update_mastery(
            db=db,
            user_id=submission.user_id,
            pattern_id=problem.pattern_id,
            is_correct=evaluation.is_correct,
        )
        mistake = None
        if not evaluation.is_correct:
            category = {
                "Compilation Error": "syntax_error",
                "Wrong Answer": "edge_case",
                "Runtime Error": "logic_error",
                "Time Limit Exceeded": "inefficient_solution",
            }.get(evaluation.status, "unknown")
            mistake = create_mistake(
                db=db,
                submission_id=new_submission.id,
                category=category,
                explanation=feedback["explanation"],
                correction=feedback["correction"],
            )
        recommendation = recommend_problem(db=db, user_id=submission.user_id)
        db.commit()
        db.refresh(new_submission)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save submission and learning records") from exc

    result = SubmissionResponse.model_validate(new_submission).model_dump()
    result["mastery"] = {
        "user_id": mastery.user_id,
        "pattern_id": mastery.pattern_id,
        "mastery_score": mastery.mastery_score,
        "confidence_score": mastery.confidence_score,
        "retention_score": mastery.retention_score,
        "total_attempts": mastery.total_attempts,
        "correct_attempts": mastery.correct_attempts,
        "consecutive_correct": mastery.consecutive_correct,
        "next_revision_at": mastery.next_revision_at,
    }
    if mistake:
        result["mistake"] = {
            "id": mistake.id,
            "submission_id": mistake.submission_id,
            "category": mistake.category,
            "explanation": mistake.explanation,
            "correction": mistake.correction,
        }
    if recommendation:
        result["recommendation"] = recommendation.model_dump()
    return result


@router.get("/", response_model=list[SubmissionResponse])
def get_submissions(db: Session = Depends(get_db)):
    return db.query(Submission).all()


@router.get("/{submission_id}", response_model=SubmissionResponse)
def get_submission(submission_id: int, db: Session = Depends(get_db)):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission
