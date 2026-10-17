"""Seed patterns, problems and console-I/O test cases.

Safe to run repeatedly: existing patterns and problems are left untouched,
except that a problem with no test cases receives the cases (and description)
defined for it in data/test_cases.json.

Seed data is validated before anything is written, so a typo in the JSON
files fails loudly instead of producing a half-seeded database.

To protect shared databases, seeding anything other than SQLite requires the
``--confirm`` flag. Usage from the ``backend`` directory:

    # Seed an isolated SQLite file regardless of DATABASE_URL / .env
    python -m app.seed --sqlite ./codex-demo.sqlite3

    # Or point DATABASE_URL at the file first
    $env:DATABASE_URL = "sqlite:///./codex-demo.sqlite3"
    python -m app.seed
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import DATABASE_URL, Base, SessionLocal, engine
from app.models import Pattern, Problem
from app.services.evaluator import EvaluationUnavailable, validate_test_cases


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

REQUIRED_PROBLEM_KEYS = ("title", "platform", "external_id", "difficulty", "pattern")


class SeedDataError(ValueError):
    """The JSON seed files are inconsistent; nothing has been written."""


def _load(name):
    with open(DATA_DIR / name, "r", encoding="utf-8") as file:
        return json.load(file)


def load_patterns():
    return _load("patterns.json")


def load_problems():
    return _load("problems.json")


def load_test_cases():
    path = DATA_DIR / "test_cases.json"
    if not path.exists():
        print(f"Warning: {path} not found; problems will be seeded without test cases.", file=sys.stderr)
        return {}
    return _load("test_cases.json")


def validate_seed_data(patterns, problems, test_cases):
    """Cross-check the three seed files. Raises SeedDataError listing every defect found."""
    errors = []

    if not isinstance(patterns, list) or not isinstance(problems, list) or not isinstance(test_cases, dict):
        raise SeedDataError(
            "Seed data is invalid: patterns.json and problems.json must be lists and "
            "test_cases.json must be an object keyed by external_id"
        )

    pattern_names = []
    for index, item in enumerate(patterns):
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name.strip():
            errors.append(f"patterns.json entry {index} has no name")
            continue
        if name in pattern_names:
            errors.append(f"patterns.json has duplicate name {name!r}")
        pattern_names.append(name)

    seen_problems = set()
    for index, item in enumerate(problems):
        if not isinstance(item, dict):
            errors.append(f"problems.json entry {index} must be an object")
            continue
        missing = [key for key in REQUIRED_PROBLEM_KEYS if not isinstance(item.get(key), str) or not item[key].strip()]
        if missing:
            errors.append(f"problems.json entry {index} is missing {missing}")
            continue
        if item["pattern"] not in pattern_names:
            errors.append(
                f"problems.json {item['platform']} {item['external_id']} uses unknown pattern {item['pattern']!r}"
            )
        key = (item["platform"], item["external_id"])
        if key in seen_problems:
            errors.append(f"problems.json has duplicate problem {item['platform']} {item['external_id']}")
        seen_problems.add(key)

    known_ids = {item.get("external_id") for item in problems if isinstance(item, dict)}
    for external_id, entry in test_cases.items():
        if external_id not in known_ids:
            errors.append(f"test_cases.json entry {external_id} does not match any problem")
        if not isinstance(entry, dict):
            errors.append(f"test_cases.json entry {external_id} must be an object")
            continue
        try:
            validate_test_cases(entry.get("test_cases"))
        except EvaluationUnavailable as exc:
            errors.append(f"test_cases.json entry {external_id}: {exc}")
            continue
        if not all(isinstance(case.get("visible"), bool) for case in entry["test_cases"]):
            errors.append(f"test_cases.json entry {external_id} has a case without a boolean 'visible' flag")
        elif not any(case["visible"] for case in entry["test_cases"]):
            errors.append(f"test_cases.json entry {external_id} has no visible sample case")

    if errors:
        raise SeedDataError("Seed data is invalid:\n  " + "\n  ".join(errors))


def seed_patterns(db, patterns=None):
    patterns = load_patterns() if patterns is None else patterns

    pattern_map = {}

    for item in patterns:
        pattern = db.query(Pattern).filter(
            Pattern.name == item["name"]
        ).first()

        if not pattern:
            pattern = Pattern(
                name=item["name"],
                description=item.get("description")
            )
            db.add(pattern)
            db.flush()

        pattern_map[item["name"]] = pattern.id

    return pattern_map


def seed_problems(db, pattern_map, problems=None, test_cases=None):
    problems = load_problems() if problems is None else problems
    test_cases = load_test_cases() if test_cases is None else test_cases

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
            url=item.get("url"),
            difficulty=item["difficulty"],
            pattern_id=pattern_map[item["pattern"]],
            description=extra.get("description"),
            test_cases=extra.get("test_cases", []),
        ))
        created += 1
    return created, updated


def seed_database(db, patterns=None, problems=None, test_cases=None):
    """Validate the seed files, then seed. Returns (created, updated).

    Commits on success; on any failure the session is rolled back so the
    database is left exactly as it was.
    """
    patterns = load_patterns() if patterns is None else patterns
    problems = load_problems() if problems is None else problems
    test_cases = load_test_cases() if test_cases is None else test_cases
    validate_seed_data(patterns, problems, test_cases)
    try:
        pattern_map = seed_patterns(db, patterns)
        result = seed_problems(db, pattern_map, problems, test_cases)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


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


def sqlite_url(path) -> str:
    """SQLAlchemy URL for a SQLite file path (absolute, or relative to the cwd)."""
    return "sqlite:///" + Path(path).expanduser().resolve().as_posix()


def summarize(db) -> dict:
    """Counts printed after seeding; tests use them to confirm reproducibility."""
    problems = db.query(Problem).all()
    return {
        "patterns": db.query(Pattern).count(),
        "problems": len(problems),
        "evaluable": sum(1 for problem in problems if problem.test_cases_available),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Seed the CodeX database.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required to seed a non-SQLite database (for example PostgreSQL).",
    )
    parser.add_argument(
        "--sqlite",
        metavar="PATH",
        help="Seed this SQLite file (created if missing) instead of DATABASE_URL. "
             "The database configured in .env is never opened.",
    )
    args = parser.parse_args(argv)

    if args.sqlite:
        target_url = sqlite_url(args.sqlite)
        target_engine = create_engine(target_url)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=target_engine)
    else:
        target_url = DATABASE_URL
        target_engine = engine
        session_factory = SessionLocal

    target = describe_database(target_url)
    if not is_sqlite(target_url) and not args.confirm:
        print(
            f"Refusing to seed {target} without --confirm.\n"
            "For an isolated demo, seed a SQLite file instead, e.g.\n"
            "  python -m app.seed --sqlite ./codex-demo.sqlite3",
            file=sys.stderr,
        )
        return 1

    try:
        patterns, problems, test_cases = load_patterns(), load_problems(), load_test_cases()
        validate_seed_data(patterns, problems, test_cases)
    except (OSError, ValueError) as exc:
        # json.JSONDecodeError and SeedDataError are both ValueErrors.
        print(f"Not seeding {target}: {exc}", file=sys.stderr)
        return 2

    print(f"Seeding {target}")
    # Non-destructive: creates missing tables only, so a brand-new SQLite
    # file works without starting the API first.
    Base.metadata.create_all(bind=target_engine)
    db = session_factory()

    try:
        created, updated = seed_database(db, patterns, problems, test_cases)
        counts = summarize(db)

        print("Database seeded successfully.")
        print(f"Patterns: {counts['patterns']}")
        print(f"Problems: {counts['problems']} ({created} created, {updated} given test cases)")
        print(f"Problems with runnable test cases: {counts['evaluable']}")
        return 0

    finally:
        db.close()
        if args.sqlite:
            target_engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
