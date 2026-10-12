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
    # Filter on the same validation used by the evaluator before ranking.
    problems = [
        problem
        for problem in db.query(Problem).order_by(Problem.id).all()
        if problem.test_cases_available
    ]
    if not problems:
        return None

    pattern_names = {
        pattern.id: pattern.name
        for pattern in db.query(Pattern).all()
    }
    mastery_by_pattern = {
        mastery.pattern_id: mastery
        for mastery in (
            db.query(PatternMastery)
            .filter(PatternMastery.user_id == user_id)
            .all()
        )
    }

    attempt_counts: dict[int, int] = {}
    correct_counts: dict[int, int] = {}
    attempted_problem_ids: set[int] = set()
    latest_attempt_rank: dict[int, int] = {}
    attempts = (
        db.query(
            Submission.problem_id,
            Submission.is_correct,
            Problem.pattern_id,
            Problem.difficulty,
        )
        .join(Problem, Problem.id == Submission.problem_id)
        .filter(Submission.user_id == user_id)
        .order_by(Submission.submitted_at.desc(), Submission.id.desc())
        .all()
    )
    for problem_id, is_correct, pattern_id, difficulty in attempts:
        attempted_problem_ids.add(problem_id)
        attempt_counts[pattern_id] = attempt_counts.get(pattern_id, 0) + 1
        if is_correct:
            correct_counts[pattern_id] = correct_counts.get(pattern_id, 0) + 1
        latest_attempt_rank.setdefault(
            pattern_id,
            DIFFICULTY_RANK.get(difficulty.lower(), 0),
        )

    available_by_pattern: dict[int, list[Problem]] = {}
    for problem in problems:
        available_by_pattern.setdefault(problem.pattern_id, []).append(problem)

    patterns_with_history = set(attempt_counts)
    patterns_with_mastery = set(mastery_by_pattern)
    known_patterns = patterns_with_history | patterns_with_mastery

    def weakness_key(pattern_id: int) -> tuple[float, float, int, int]:
        mastery = mastery_by_pattern.get(pattern_id)
        attempts_for_pattern = attempt_counts.get(pattern_id, 0)
        correct_for_pattern = correct_counts.get(pattern_id, 0)
        observed_accuracy = (
            correct_for_pattern / attempts_for_pattern * 100
            if attempts_for_pattern
            else 0.0
        )
        effective_score = (
            mastery.mastery_score if mastery is not None else observed_accuracy
        )
        return (
            effective_score,
            observed_accuracy,
            -attempts_for_pattern,
            pattern_id,
        )

    ranked_patterns = sorted(known_patterns, key=weakness_key)
    if not ranked_patterns:
        starter = min(
            problems,
            key=lambda problem: (
                problem.id in attempted_problem_ids,
                DIFFICULTY_RANK.get(problem.difficulty.lower(), 3),
                problem.id,
            ),
        )
        return _response(
            starter,
            pattern_names,
            reason="Start with this available, unattempted problem to build your pattern mastery.",
            priority=50.0,
        )

    for pattern_id in ranked_patterns:
        pattern_problems = available_by_pattern.get(pattern_id, [])
        if not pattern_problems:
            continue

        unattempted = [
            problem
            for problem in pattern_problems
            if problem.id not in attempted_problem_ids
        ]
        candidates = unattempted or pattern_problems
        mastery = mastery_by_pattern.get(pattern_id)
        attempts_for_pattern = attempt_counts.get(pattern_id, 0)
        observed_accuracy = (
            correct_counts.get(pattern_id, 0) / attempts_for_pattern * 100
            if attempts_for_pattern
            else None
        )
        score = (
            mastery.mastery_score
            if mastery is not None
            else observed_accuracy if observed_accuracy is not None else 0.0
        )
        pattern_name = pattern_names.get(pattern_id, "this pattern")
        history_note = (
            f" Based on {attempts_for_pattern} prior attempt"
            f"{'s' if attempts_for_pattern != 1 else ''}"
            + (
                f" ({observed_accuracy:.0f}% correct)."
                if observed_accuracy is not None
                else "."
            )
        )
        repeat_note = (
            " All available problems in this pattern have been attempted."
            if not unattempted
            else ""
        )

        if score < 40:
            problem = min(
                candidates,
                key=lambda item: (
                    DIFFICULTY_RANK.get(item.difficulty.lower(), 3),
                    item.id,
                ),
            )
            reason = (
                f"Practice {pattern_name} with a foundational problem because "
                f"mastery is below 40.{history_note}{repeat_note}"
            )
            priority = 100.0 - score
        elif score <= 70:
            target_rank = latest_attempt_rank.get(pattern_id, 0)
            problem = min(
                candidates,
                key=lambda item: (
                    abs(DIFFICULTY_RANK.get(item.difficulty.lower(), 3) - target_rank),
                    DIFFICULTY_RANK.get(item.difficulty.lower(), 3),
                    item.id,
                ),
            )
            reason = (
                f"Continue practicing {pattern_name} to strengthen its developing "
                "mastery, using a problem near your most recent difficulty."
                f"{history_note}{repeat_note}"
            )
            priority = 70.0 - score
        else:
            problem = max(
                candidates,
                key=lambda item: (
                    DIFFICULTY_RANK.get(item.difficulty.lower(), -1),
                    -item.id,
                ),
            )
            reason = (
                f"Your mastery of {pattern_name} is strong; try a harder available "
                f"problem to keep progressing.{history_note}{repeat_note}"
            )
            priority = max(1.0, 100.0 - score)

        return _response(problem, pattern_names, reason=reason, priority=priority)

    fallback = min(
        problems,
        key=lambda problem: (
            problem.id in attempted_problem_ids,
            DIFFICULTY_RANK.get(problem.difficulty.lower(), 3),
            problem.id,
        ),
    )
    weakest_pattern = ranked_patterns[0]
    pattern_name = pattern_names.get(weakest_pattern, "your weakest pattern")
    repeat_note = (
        " All available problems have been attempted."
        if all(problem.id in attempted_problem_ids for problem in problems)
        else ""
    )
    return _response(
        fallback,
        pattern_names,
        reason=(
            f"No evaluable problems are available for {pattern_name}; "
            f"practice this other available problem instead.{repeat_note}"
        ),
        priority=max(1.0, 100.0 - weakness_key(weakest_pattern)[0]),
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
