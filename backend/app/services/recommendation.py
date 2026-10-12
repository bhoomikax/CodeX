from sqlalchemy.orm import Session

from app.models.mastery import PatternMastery
from app.models.pattern import Pattern
from app.models.problem import Problem
from app.models.submission import Submission
from app.schemas.recommendation import RecommendationResponse


DIFFICULTY_RANK = {
    "easy": 0,
    "medium": 1,
    "hard": 2,
}


def recommend_problem(
    db: Session,
    user_id: int,
) -> RecommendationResponse | None:
    problems = [
        problem
        for problem in db.query(Problem).order_by(Problem.id).all()
        if problem.test_cases
    ]
    if not problems:
        return None

    patterns = {
        pattern.id: pattern.name
        for pattern in db.query(Pattern).all()
    }
    completed_problem_ids = {
        problem_id
        for (problem_id,) in (
            db.query(Submission.problem_id)
            .filter(
                Submission.user_id == user_id,
                Submission.is_correct.is_(True),
            )
            .distinct()
            .all()
        )
    }
    available = [
        problem
        for problem in problems
        if problem.id not in completed_problem_ids
    ]
    if not available:
        return None

    mastery_records = (
        db.query(PatternMastery)
        .filter(PatternMastery.user_id == user_id)
        .order_by(PatternMastery.mastery_score, PatternMastery.pattern_id)
        .all()
    )
    available_by_pattern: dict[int, list[Problem]] = {}
    for problem in available:
        available_by_pattern.setdefault(problem.pattern_id, []).append(problem)

    if not mastery_records:
        starter = min(
            available,
            key=lambda problem: (
                DIFFICULTY_RANK.get(problem.difficulty.lower(), 3),
                problem.id,
            ),
        )
        return _response(
            starter,
            patterns,
            reason="Start with this available problem to build your pattern mastery.",
            priority=50.0,
        )

    weakest = mastery_records[0]
    candidates = available_by_pattern.get(weakest.pattern_id, [])
    mastery_score = weakest.mastery_score

    if mastery_score < 40:
        reason = (
            f"Practice {patterns.get(weakest.pattern_id, 'this pattern')} "
            "with foundational problems because your mastery is below 40."
        )
        if candidates:
            problem = min(
                candidates,
                key=lambda item: (
                    DIFFICULTY_RANK.get(item.difficulty.lower(), 3),
                    item.id,
                ),
            )
        priority = 100.0 - mastery_score
    elif mastery_score <= 70:
        reason = (
            f"Continue practicing {patterns.get(weakest.pattern_id, 'this pattern')} "
            "to strengthen your developing mastery."
        )
        if candidates:
            last_solved = (
                db.query(Problem)
                .join(Submission, Submission.problem_id == Problem.id)
                .filter(
                    Submission.user_id == user_id,
                    Submission.is_correct.is_(True),
                    Problem.pattern_id == weakest.pattern_id,
                )
                .order_by(Submission.submitted_at.desc(), Submission.id.desc())
                .first()
            )
            target_rank = (
                DIFFICULTY_RANK.get(last_solved.difficulty.lower(), 0)
                if last_solved
                else 0
            )
            problem = min(
                candidates,
                key=lambda item: (
                    abs(DIFFICULTY_RANK.get(item.difficulty.lower(), 3) - target_rank),
                    item.id,
                ),
            )
        priority = 70.0 - mastery_score
    else:
        reason = (
            f"Your mastery of {patterns.get(weakest.pattern_id, 'this pattern')} is strong; "
            "try a harder unsolved problem to keep progressing."
        )
        if candidates:
            problem = max(
                candidates,
                key=lambda item: (
                    DIFFICULTY_RANK.get(item.difficulty.lower(), -1),
                    -item.id,
                ),
            )
        priority = max(1.0, 100.0 - mastery_score)

    if not candidates:
        fallback = available[0]
        reason = (
            f"No unsolved problem remains for {patterns.get(weakest.pattern_id, 'your weakest pattern')}; "
            "review this available problem instead."
        )
        problem = fallback

    return _response(
        problem,
        patterns,
        reason=reason,
        priority=priority,
    )


def _response(
    problem: Problem,
    patterns: dict[int, str],
    reason: str,
    priority: float,
) -> RecommendationResponse:
    return RecommendationResponse(
        problem_id=problem.id,
        title=problem.title,
        difficulty=problem.difficulty,
        pattern=patterns.get(problem.pattern_id, "Unknown pattern"),
        reason=reason,
        priority=priority,
    )
