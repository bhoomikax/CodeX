from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.mastery import PatternMastery


def update_mastery(
    db: Session,
    user_id: int,
    pattern_id: int,
    is_correct: bool
):
    mastery = (
        db.query(PatternMastery)
        .filter(
            PatternMastery.user_id == user_id,
            PatternMastery.pattern_id == pattern_id
        )
        .first()
    )

    if not mastery:
        mastery = PatternMastery(
        user_id=user_id,
        pattern_id=pattern_id,
        mastery_score=0.0,
        confidence_score=0.0,
        retention_score=0.0,
        total_attempts=0,
        correct_attempts=0,
        consecutive_correct=0
    )
        db.add(mastery)

    # Update attempt statistics
    mastery.total_attempts += 1

    if is_correct:
        mastery.correct_attempts += 1
        mastery.consecutive_correct += 1
    else:
        mastery.consecutive_correct = 0

    # Calculate success rate
    success_rate = (
        mastery.correct_attempts / mastery.total_attempts
    ) * 100

    # Consecutive-correct bonus, capped at 20 points
    consecutive_bonus = min(
        mastery.consecutive_correct * 5,
        20
    )

    # Calculate mastery
    mastery.mastery_score = min(
        success_rate * 0.8 + consecutive_bonus,
        100
    )

    # Confidence grows with successful performance
    mastery.confidence_score = min(
        mastery.mastery_score * 0.9,
        100
    )

    # Retention starts from mastery and is adjusted over time
    mastery.retention_score = min(
        mastery.mastery_score,
        100
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    mastery.last_attempted_at = now

    # Revision interval based on mastery
    revision_days = max(
        1,
        int(mastery.mastery_score / 20)
    )

    mastery.next_revision_at = (
        now
        + timedelta(days=revision_days)
    )

    mastery.updated_at = now

    return mastery
