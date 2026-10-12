from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.mastery import PatternMastery
from app.models.pattern import Pattern
from app.models.problem import Problem
from app.schemas.revision import RevisionRecommendationResponse
from app.services.recommendation import DIFFICULTY_RANK


def get_due_revisions(
    db: Session,
    user_id: int,
    now: datetime | None = None,
) -> list[RevisionRecommendationResponse]:
    current_time = now or datetime.now(UTC).replace(tzinfo=None)
    due_patterns = (
        db.query(PatternMastery, Pattern)
        .join(Pattern, Pattern.id == PatternMastery.pattern_id)
        .filter(
            PatternMastery.user_id == user_id,
            PatternMastery.next_revision_at.is_not(None),
            PatternMastery.next_revision_at <= current_time,
        )
        .order_by(
            PatternMastery.mastery_score,
            PatternMastery.next_revision_at,
            PatternMastery.pattern_id,
        )
        .all()
    )
    if not due_patterns:
        return []

    pattern_ids = [mastery.pattern_id for mastery, _ in due_patterns]
    problems_by_pattern: dict[int, list[Problem]] = {}
    for problem in (
        db.query(Problem)
        .filter(Problem.pattern_id.in_(pattern_ids))
        .order_by(Problem.id)
        .all()
    ):
        if problem.test_cases_available:
            problems_by_pattern.setdefault(problem.pattern_id, []).append(problem)

    recommendations = []
    for mastery, pattern in due_patterns:
        available = problems_by_pattern.get(pattern.id, [])
        if not available:
            continue

        if mastery.mastery_score < 40:
            problem = min(
                available,
                key=lambda item: (
                    DIFFICULTY_RANK.get(item.difficulty.lower(), 3),
                    item.id,
                ),
            )
            reason = (
                f"Review {pattern.name}: mastery is below 40, so this foundational "
                f"{problem.difficulty.lower()} problem is selected."
            )
        elif mastery.mastery_score <= 70:
            problem = min(
                available,
                key=lambda item: (
                    abs(DIFFICULTY_RANK.get(item.difficulty.lower(), 3) - 1),
                    item.id,
                ),
            )
            reason = (
                f"Review {pattern.name}: its revision is due and mastery is developing; "
                f"this {problem.difficulty.lower()} problem is closest to the medium level."
            )
        else:
            problem = max(
                available,
                key=lambda item: (
                    DIFFICULTY_RANK.get(item.difficulty.lower(), -1),
                    -item.id,
                ),
            )
            reason = (
                f"Review {pattern.name}: its revision is due despite strong mastery, "
                f"so this challenging {problem.difficulty.lower()} problem reinforces retention."
            )

        recommendations.append(
            RevisionRecommendationResponse(
                pattern_id=pattern.id,
                pattern_name=pattern.name,
                mastery_score=mastery.mastery_score,
                due_at=mastery.next_revision_at,
                problem_id=problem.id,
                problem_title=problem.title,
                difficulty=problem.difficulty,
                reason=reason,
                priority=100.0 - mastery.mastery_score,
            )
        )

    return recommendations
