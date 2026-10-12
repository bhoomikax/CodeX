import json
from pathlib import Path

from app.database import SessionLocal
from app.models import Pattern, Problem


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"


def seed_patterns(db):
    with open(DATA_DIR / "patterns.json", "r", encoding="utf-8") as file:
        patterns = json.load(file)

    pattern_map = {}

    for item in patterns:
        pattern = db.query(Pattern).filter(
            Pattern.name == item["name"]
        ).first()

        if not pattern:
            pattern = Pattern(
                name=item["name"],
                description=item["description"]
            )
            db.add(pattern)
            db.flush()

        pattern_map[item["name"]] = pattern.id

    return pattern_map


def seed_problems(db, pattern_map):
    with open(DATA_DIR / "problems.json", "r", encoding="utf-8") as file:
        problems = json.load(file)

    for item in problems:
        existing = db.query(Problem).filter(
            Problem.external_id == item["external_id"],
            Problem.platform == item["platform"]
        ).first()

        if existing:
            if item["external_id"] == "704" and not existing.test_cases:
                existing.description = (
                    "Console I/O demonstration: read n, then n sorted integers, then target. "
                    "Print the zero-based index of target, or -1 if it is absent."
                )
                existing.test_cases = [
                    {"input": "6\n-1 0 3 5 9 12\n9\n", "expected_output": "4\n", "visible": True},
                    {"input": "6\n-1 0 3 5 9 12\n2\n", "expected_output": "-1\n", "visible": True},
                    {"input": "1\n5\n5\n", "expected_output": "0\n", "visible": False},
                ]
            continue

        problem = Problem(
            title=item["title"],
            platform=item["platform"],
            external_id=item["external_id"],
            url=item["url"],
            difficulty=item["difficulty"],
            pattern_id=pattern_map[item["pattern"]],
            description=(
                "Console I/O demonstration: read n, then n sorted integers, then target. "
                "Print the zero-based index of target, or -1 if it is absent."
                if item["external_id"] == "704"
                else None
            ),
            test_cases=(
                [
                    {"input": "6\n-1 0 3 5 9 12\n9\n", "expected_output": "4\n", "visible": True},
                    {"input": "6\n-1 0 3 5 9 12\n2\n", "expected_output": "-1\n", "visible": True},
                    {"input": "1\n5\n5\n", "expected_output": "0\n", "visible": False},
                ]
                if item["external_id"] == "704"
                else []
            ),
        )

        db.add(problem)


def main():
    db = SessionLocal()

    try:
        pattern_map = seed_patterns(db)
        seed_problems(db, pattern_map)
        db.commit()

        print("Database seeded successfully.")

        print(f"Patterns: {db.query(Pattern).count()}")
        print(f"Problems: {db.query(Problem).count()}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
