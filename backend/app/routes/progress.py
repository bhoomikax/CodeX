from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Pattern, PatternMastery, Problem, Submission, User
from app.schemas.progress import (
    LearnerProgressResponse,
    PatternProgressResponse,
    RecentSubmissionResponse,
)

router = APIRouter(prefix="/progress", tags=["Progress"])
RECENT_SUBMISSION_LIMIT = 10


def _accuracy_percentage(correct_attempts: int, total_attempts: int) -> float:
    if total_attempts == 0:
        return 0.0
    return round(correct_attempts / total_attempts * 100, 2)


@router.get("/", response_model=LearnerProgressResponse)
def get_progress(
    user_id: int = Query(gt=0, description="Learner whose progress should be returned"),
    db: Session = Depends(get_db),
):
    """Return persisted attempt statistics, pattern mastery, and recent activity for one learner."""
    user = db.query(User.id).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    attempt_stats = (
        db.query(
            Problem.pattern_id.label("pattern_id"),
            func.count(Submission.id).label("total_attempts"),
            func.coalesce(
                func.sum(case((Submission.is_correct.is_(True), 1), else_=0)),
                0,
            ).label("correct_attempts"),
        )
        .join(Problem, Problem.id == Submission.problem_id)
        .filter(Submission.user_id == user_id)
        .group_by(Problem.pattern_id)
        .subquery()
    )
    pattern_rows = (
        db.query(
            Pattern,
            attempt_stats.c.total_attempts,
            attempt_stats.c.correct_attempts,
            PatternMastery,
        )
        .join(attempt_stats, attempt_stats.c.pattern_id == Pattern.id)
        .outerjoin(
            PatternMastery,
            and_(
                PatternMastery.user_id == user_id,
                PatternMastery.pattern_id == Pattern.id,
            ),
        )
        .order_by(Pattern.id)
        .all()
    )

    patterns = [
        PatternProgressResponse(
            pattern_id=pattern.id,
            pattern_name=pattern.name,
            mastery_score=mastery.mastery_score if mastery else 0.0,
            confidence_score=mastery.confidence_score if mastery else 0.0,
            retention_score=mastery.retention_score if mastery else 0.0,
            total_attempts=total_attempts,
            correct_attempts=correct_attempts,
            accuracy_percentage=_accuracy_percentage(correct_attempts, total_attempts),
            consecutive_correct=mastery.consecutive_correct if mastery else 0,
        )
        for pattern, total_attempts, correct_attempts, mastery in pattern_rows
    ]
    total_attempts = sum(pattern.total_attempts for pattern in patterns)
    correct_attempts = sum(pattern.correct_attempts for pattern in patterns)

    recent_rows = (
        db.query(Submission, Problem, Pattern)
        .join(Problem, Problem.id == Submission.problem_id)
        .join(Pattern, Pattern.id == Problem.pattern_id)
        .filter(Submission.user_id == user_id)
        .order_by(Submission.submitted_at.desc(), Submission.id.desc())
        .limit(RECENT_SUBMISSION_LIMIT)
        .all()
    )
    recent_submissions = [
        RecentSubmissionResponse(
            id=submission.id,
            problem_id=problem.id,
            problem_title=problem.title,
            pattern_id=pattern.id,
            pattern_name=pattern.name,
            language=submission.language,
            status=submission.status,
            is_correct=submission.is_correct,
            submitted_at=submission.submitted_at,
        )
        for submission, problem, pattern in recent_rows
    ]

    strongest_pattern = max(
        patterns,
        key=lambda pattern: (pattern.mastery_score, -pattern.pattern_id),
        default=None,
    )
    weakest_pattern = min(
        patterns,
        key=lambda pattern: (pattern.mastery_score, pattern.pattern_id),
        default=None,
    )

    return LearnerProgressResponse(
        user_id=user_id,
        total_attempts=total_attempts,
        correct_attempts=correct_attempts,
        accuracy_percentage=_accuracy_percentage(correct_attempts, total_attempts),
        patterns=patterns,
        strongest_pattern=strongest_pattern,
        weakest_pattern=weakest_pattern,
        recent_submissions=recent_submissions,
    )
