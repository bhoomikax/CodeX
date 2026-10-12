"""Seed patterns, problems and console-I/O test cases.

Safe to run repeatedly: existing patterns and problems are left untouched,
except that a problem with no test cases receives the cases (and description)
defined for it in data/test_cases.json.

To protect shared databases, seeding anything other than SQLite requires the
``--confirm`` flag. Usage from the ``backend`` directory:

    $env:DATABASE_URL = "sqlite:///./codex-demo.sqlite3"
    python -m app.seed
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from app.database import DATABASE_URL, Base, SessionLocal, engine
from app.models import Pattern, Problem


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"


def load_test_cases():
    path = DATA_DIR / "test_cases.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


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
    test_cases = load_test_cases()

    created = updated = 0
    for item in problems:
        extra = test_cases.get(item["external_id"], {})
        existing = db.query(Problem).filter(
            Problem.external_id == item["external_id"],
            Problem.platform == item["platform"]
        ).first()

        if existing:
            # Only fill in cases for problems that have none; never overwrite
            # cases somebody has configured by hand.
            if extra.get("test_cases") and not existing.test_cases:
                existing.test_cases = extra["test_cases"]
                if extra.get("description"):
                    existing.description = extra["description"]
                updated += 1
            continue

        db.add(Problem(
            title=item["title"],
            platform=item["platform"],
            external_id=item["external_id"],
            url=item["url"],
            difficulty=item["difficulty"],
            pattern_id=pattern_map[item["pattern"]],
            description=extra.get("description"),
            test_cases=extra.get("test_cases", []),
        ))
        created += 1
    return created, updated


def describe_database(url: str) -> str:
    """Human-readable target without credentials."""
    parsed = urlparse(url or "")
    if parsed.scheme.startswith("sqlite"):
        return f"sqlite file {parsed.path.lstrip('/') or ':memory:'}"
    host = parsed.hostname or "?"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme} database {parsed.path.lstrip('/')} on {host}{port}"


def is_sqlite(url: str) -> bool:
    return urlparse(url or "").scheme.startswith("sqlite")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Seed the CodeX/PatternIQ database.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required to seed a non-SQLite database (for example PostgreSQL).",
    )
    args = parser.parse_args(argv)

    target = describe_database(DATABASE_URL)
    if not is_sqlite(DATABASE_URL) and not args.confirm:
        print(
            f"Refusing to seed {target} without --confirm.\n"
            "For an isolated demo, set DATABASE_URL to a SQLite file first, e.g.\n"
            '  $env:DATABASE_URL = "sqlite:///./codex-demo.sqlite3"',
            file=sys.stderr,
        )
        return 1

    print(f"Seeding {target}")
    # Non-destructive: creates missing tables only, so a brand-new SQLite
    # file works without starting the API first.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        pattern_map = seed_patterns(db)
        created, updated = seed_problems(db, pattern_map)
        db.commit()

        print("Database seeded successfully.")
        print(f"Patterns: {db.query(Pattern).count()}")
        print(f"Problems: {db.query(Problem).count()} ({created} created, {updated} given test cases)")
        evaluable = sum(1 for problem in db.query(Problem).all() if problem.test_cases_available)
        print(f"Problems with runnable test cases: {evaluable}")
        return 0

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
