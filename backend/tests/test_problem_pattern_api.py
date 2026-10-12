"""Problem and pattern data readiness.

Covers three things the demo depends on:

* the three seed files in ``data/`` are mutually consistent and a
  representative set of problems has runnable input/expected-output cases;
* ``python -m app.seed --sqlite PATH`` seeds a brand-new SQLite file
  reproducibly without opening the database configured in ``.env``;
* the read-only problem and pattern endpoints return the documented schema
  and handle unknown IDs, malformed IDs and empty tables, exercised through
  the real FastAPI routing/serialisation layer.
"""
import asyncio
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import seed
from app.database import Base, get_db
from app.models import Pattern, Problem
from app.routes import patterns as pattern_routes
from app.routes import problems as problem_routes
from app.schemas.pattern import PatternResponse
from app.schemas.problem import ProblemResponse


PROBLEM_FIELDS = {
    "id", "title", "platform", "external_id", "url", "difficulty",
    "pattern_id", "description", "test_cases_available", "sample_cases",
}
PATTERN_FIELDS = {"id", "name", "description"}

# A small cross-section of the catalog that the demo, README and live test
# plan rely on. Each must have verified cases including at least one hidden one.
REPRESENTATIVE_PROBLEMS = {
    "704": "Binary Search",
    "167": "Two Pointers",
    "3": "Sliding Window",
    "217": "Hashing",
    "20": "Stack",
    "70": "Dynamic Programming",
    "121": "Greedy",
}


def memory_engine():
    """In-memory SQLite shared across threads (FastAPI runs sync routes in a threadpool)."""
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


class AsgiClient:
    """Tiny in-process HTTP client so the tests need neither httpx nor a server."""

    def __init__(self, app):
        self.app = app

    def get(self, path, query=""):
        return asyncio.run(self._request("GET", path, query))

    async def _request(self, method, path, query):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await self.app(scope, receive, send)
        start = next(m for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
        payload = json.loads(body) if headers.get("content-type", "").startswith("application/json") else body
        return start["status"], headers, payload


class SeedFileIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = seed.load_patterns()
        cls.problems = seed.load_problems()
        cls.test_cases = seed.load_test_cases()

    def test_shipped_seed_files_are_consistent(self):
        seed.validate_seed_data(self.patterns, self.problems, self.test_cases)

    def test_problem_identity_is_unique(self):
        keys = [(p["platform"], p["external_id"]) for p in self.problems]
        self.assertEqual(len(keys), len(set(keys)))
        names = [p["name"] for p in self.patterns]
        self.assertEqual(len(names), len(set(names)))

    def test_every_problem_pattern_exists(self):
        names = {p["name"] for p in self.patterns}
        for problem in self.problems:
            self.assertIn(problem["pattern"], names, problem["title"])

    def test_representative_problems_have_visible_and_hidden_cases(self):
        by_id = {p["external_id"]: p for p in self.problems}
        for external_id, pattern in REPRESENTATIVE_PROBLEMS.items():
            with self.subTest(problem=external_id):
                self.assertEqual(by_id[external_id]["pattern"], pattern)
                entry = self.test_cases[external_id]
                self.assertTrue(entry["description"].startswith("Console I/O"))
                cases = entry["test_cases"]
                self.assertGreaterEqual(len(cases), 2)
                self.assertTrue(any(case["visible"] for case in cases))
                self.assertTrue(any(not case["visible"] for case in cases))
                for case in cases:
                    self.assertIsInstance(case["input"], str)
                    self.assertIsInstance(case["expected_output"], str)
                    self.assertTrue(case["expected_output"].endswith("\n"))

    def test_evaluable_problems_cover_every_difficulty(self):
        evaluable = [p for p in self.problems if p["external_id"] in self.test_cases]
        self.assertEqual({p["difficulty"] for p in evaluable}, {"Easy", "Medium", "Hard"})

    def test_validation_reports_every_defect_at_once(self):
        patterns = [{"name": "Two Pointers"}, {"name": "Two Pointers"}]
        problems = [
            {"title": "A", "platform": "LeetCode", "external_id": "1", "difficulty": "Easy", "pattern": "Two Pointers"},
            {"title": "B", "platform": "LeetCode", "external_id": "1", "difficulty": "Easy", "pattern": "Two Pointers"},
            {"title": "C", "platform": "LeetCode", "external_id": "2", "difficulty": "Easy", "pattern": "Nope"},
            {"title": "", "platform": "LeetCode", "external_id": "3", "difficulty": "Easy", "pattern": "Two Pointers"},
        ]
        test_cases = {
            "999": {"description": "x", "test_cases": [{"input": "1\n", "expected_output": "1\n", "visible": True}]},
            "1": {"description": "x", "test_cases": [{"input": "1\n", "expected_output": 1, "visible": True}]},
            "2": {"description": "x", "test_cases": [{"input": "1\n", "expected_output": "1\n", "visible": False}]},
            "3": {"description": "x", "test_cases": [{"input": "1\n", "expected_output": "1\n"}]},
        }
        with self.assertRaises(seed.SeedDataError) as error:
            seed.validate_seed_data(patterns, problems, test_cases)
        message = str(error.exception)
        for fragment in (
            "duplicate name 'Two Pointers'",
            "duplicate problem LeetCode 1",
            "unknown pattern 'Nope'",
            "entry 3 is missing ['title']",
            "entry 999 does not match any problem",
            "entry 1: Evaluation is unavailable",
            "entry 2 has no visible sample case",
            "entry 3 has a case without a boolean 'visible' flag",
        ):
            self.assertIn(fragment, message)

    def test_validation_rejects_wrong_top_level_types(self):
        with self.assertRaises(seed.SeedDataError):
            seed.validate_seed_data({}, [], {})
        with self.assertRaises(seed.SeedDataError):
            seed.validate_seed_data([], [], [])


class SeedCommandTests(unittest.TestCase):
    """``python -m app.seed --sqlite PATH`` against a brand-new file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = Path(self.tmp.name) / "demo.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def run_seed(self, *argv):
        """Run the CLI quietly; returns (exit_code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = seed.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def snapshot(self):
        engine = create_engine(seed.sqlite_url(self.path))
        session = sessionmaker(bind=engine)()
        try:
            patterns = [(p.id, p.name) for p in session.query(Pattern).order_by(Pattern.id)]
            problems = [
                (p.id, p.platform, p.external_id, p.pattern_id, p.description, json.dumps(p.test_cases, sort_keys=True))
                for p in session.query(Problem).order_by(Problem.id)
            ]
            return patterns, problems, seed.summarize(session)
        finally:
            session.close()
            engine.dispose()

    @patch("app.seed.engine")
    @patch("app.seed.SessionLocal")
    @patch("app.seed.DATABASE_URL", "postgresql://user:secret@db.example:5433/codex")
    def test_sqlite_flag_never_opens_the_configured_database(self, session_factory, configured_engine):
        self.assertFalse(self.path.exists())
        code, out, err = self.run_seed("--sqlite", str(self.path))
        self.assertEqual(code, 0, err)
        self.assertTrue(self.path.exists())
        self.assertIn("Seeding sqlite file", out)
        self.assertNotIn("secret", out + err)
        session_factory.assert_not_called()
        configured_engine.assert_not_called()
        self.assertFalse(configured_engine.method_calls)

    def test_fresh_file_is_seeded_deterministically_and_idempotently(self):
        code, out, err = self.run_seed("--sqlite", str(self.path))
        self.assertEqual(code, 0, err)
        patterns, problems, counts = self.snapshot()
        self.assertIn(f"Problems: {counts['problems']} ({counts['problems']} created, 0 given test cases)", out)
        self.assertIn(f"Problems with runnable test cases: {counts['evaluable']}", out)

        expected_patterns = [item["name"] for item in seed.load_patterns()]
        self.assertEqual([name for _, name in patterns], expected_patterns)
        self.assertEqual([pid for pid, _ in patterns], list(range(1, len(expected_patterns) + 1)))

        expected_problems = seed.load_problems()
        self.assertEqual([p[2] for p in problems], [item["external_id"] for item in expected_problems])
        self.assertEqual([p[0] for p in problems], list(range(1, len(expected_problems) + 1)))
        # The README tells people Binary Search is problem 11 on a fresh database.
        self.assertEqual(problems[10][2], "704")

        test_cases = seed.load_test_cases()
        self.assertEqual(counts, {
            "patterns": len(expected_patterns),
            "problems": len(expected_problems),
            "evaluable": len(test_cases),
        })
        for _, _, external_id, _, description, cases in problems:
            if external_id in test_cases:
                self.assertEqual(json.loads(cases), test_cases[external_id]["test_cases"])
                self.assertEqual(description, test_cases[external_id]["description"])
            else:
                self.assertEqual(json.loads(cases), [])
                self.assertIsNone(description)

        # A second run is a no-op and leaves every row byte-for-byte identical.
        code, out, _ = self.run_seed("--sqlite", str(self.path))
        self.assertEqual(code, 0)
        self.assertIn("(0 created, 0 given test cases)", out)
        self.assertEqual(self.snapshot(), (patterns, problems, counts))

    def test_invalid_seed_data_aborts_before_touching_the_file(self):
        broken = seed.load_problems()
        broken[0] = dict(broken[0], pattern="Not A Pattern")
        with patch("app.seed.load_problems", return_value=broken):
            code, _, err = self.run_seed("--sqlite", str(self.path))
        self.assertEqual(code, 2)
        self.assertIn("unknown pattern 'Not A Pattern'", err)
        self.assertFalse(self.path.exists())

    def test_seed_database_rolls_back_when_seeding_fails(self):
        engine = memory_engine()
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        try:
            with patch("app.seed.seed_problems", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    seed.seed_database(session)
            self.assertEqual(session.query(Pattern).count(), 0)
            self.assertEqual(session.query(Problem).count(), 0)
        finally:
            session.close()
            engine.dispose()

    def test_sqlite_url_is_absolute(self):
        url = seed.sqlite_url("relative/demo.sqlite3")
        self.assertTrue(url.startswith("sqlite:///"))
        self.assertTrue(Path(url[len("sqlite:///"):]).is_absolute())
        self.assertTrue(seed.is_sqlite(url))


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = memory_engine()
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.session = self.Session()

        app = FastAPI()
        app.include_router(problem_routes.router)
        app.include_router(pattern_routes.router)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = AsgiClient(app)

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()


class EmptyDatabaseApiTests(ApiTestCase):
    def test_list_endpoints_return_empty_lists(self):
        for path in ("/problems/", "/patterns/"):
            with self.subTest(path=path):
                status, headers, body = self.client.get(path)
                self.assertEqual(status, 200)
                self.assertTrue(headers["content-type"].startswith("application/json"))
                self.assertEqual(body, [])

    def test_unknown_ids_return_404_with_detail(self):
        for path, detail in (
            ("/problems/1", "Problem not found"),
            ("/problems/-1", "Problem not found"),
            ("/patterns/1", "Pattern not found"),
            ("/patterns/1/problems", "Pattern not found"),
        ):
            with self.subTest(path=path):
                status, _, body = self.client.get(path)
                self.assertEqual(status, 404)
                self.assertEqual(body, {"detail": detail})

    def test_non_integer_ids_are_rejected_with_422(self):
        for path in ("/problems/abc", "/problems/1.5", "/patterns/abc", "/patterns/abc/problems"):
            with self.subTest(path=path):
                status, _, body = self.client.get(path)
                self.assertEqual(status, 422)
                self.assertEqual(body["detail"][0]["loc"][:1], ["path"])


class SeededApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        seed.seed_database(self.session)
        self.test_cases = seed.load_test_cases()
        self.binary_search = self.session.query(Problem).filter_by(external_id="704").one()
        self.tree_problem = self.session.query(Problem).filter_by(external_id="104").one()

    def test_problem_list_matches_schema_and_hides_test_cases(self):
        status, _, body = self.client.get("/problems/")
        self.assertEqual(status, 200)
        self.assertEqual(len(body), self.session.query(Problem).count())
        self.assertEqual([item["id"] for item in body], sorted(item["id"] for item in body))
        for item in body:
            self.assertEqual(set(item), PROBLEM_FIELDS)
            self.assertNotIn("test_cases", item)
            ProblemResponse.model_validate(item)  # round-trips through the published schema
            self.assertEqual(item["test_cases_available"], item["external_id"] in self.test_cases)
            for sample in item["sample_cases"]:
                self.assertEqual(set(sample), {"input", "expected_output"})

    def test_single_problem_exposes_only_visible_cases(self):
        status, _, body = self.client.get(f"/problems/{self.binary_search.id}")
        self.assertEqual(status, 200)
        self.assertEqual(body["title"], "Binary Search")
        self.assertEqual(body["external_id"], "704")
        self.assertTrue(body["test_cases_available"])
        self.assertTrue(body["description"].startswith("Console I/O"))
        visible = [
            {"input": c["input"], "expected_output": c["expected_output"]}
            for c in self.test_cases["704"]["test_cases"] if c["visible"]
        ]
        hidden = [c for c in self.test_cases["704"]["test_cases"] if not c["visible"]]
        self.assertTrue(hidden, "the demo problem must keep at least one hidden case")
        self.assertEqual(body["sample_cases"], visible)
        for case in hidden:
            self.assertNotIn({"input": case["input"], "expected_output": case["expected_output"]}, body["sample_cases"])

    def test_problem_without_cases_is_reported_as_not_evaluable(self):
        status, _, body = self.client.get(f"/problems/{self.tree_problem.id}")
        self.assertEqual(status, 200)
        self.assertFalse(body["test_cases_available"])
        self.assertEqual(body["sample_cases"], [])
        self.assertIsNone(body["description"])
        self.assertEqual(body["url"], "https://leetcode.com/problems/maximum-depth-of-binary-tree/")

    def test_pattern_list_matches_schema_and_seed_order(self):
        status, _, body = self.client.get("/patterns/")
        self.assertEqual(status, 200)
        self.assertEqual([item["name"] for item in body], [p["name"] for p in seed.load_patterns()])
        for item in body:
            self.assertEqual(set(item), PATTERN_FIELDS)
            PatternResponse.model_validate(item)
            self.assertTrue(item["description"])

    def test_single_pattern_and_its_problems(self):
        pattern_id = self.binary_search.pattern_id
        status, _, body = self.client.get(f"/patterns/{pattern_id}")
        self.assertEqual(status, 200)
        self.assertEqual(body["name"], "Binary Search")

        status, _, problems = self.client.get(f"/patterns/{pattern_id}/problems")
        self.assertEqual(status, 200)
        expected = sorted(p["external_id"] for p in seed.load_problems() if p["pattern"] == "Binary Search")
        self.assertEqual(sorted(p["external_id"] for p in problems), expected)
        self.assertTrue(all(p["pattern_id"] == pattern_id for p in problems))
        self.assertEqual([p["id"] for p in problems], sorted(p["id"] for p in problems))
        for item in problems:
            self.assertEqual(set(item), PROBLEM_FIELDS)

    def test_pattern_with_no_problems_returns_empty_list(self):
        empty = Pattern(name="Bit Manipulation", description="No seeded problems yet.")
        self.session.add(empty)
        self.session.commit()
        status, _, body = self.client.get(f"/patterns/{empty.id}/problems")
        self.assertEqual(status, 200)
        self.assertEqual(body, [])

    def test_unknown_ids_still_404_on_a_populated_database(self):
        missing = self.session.query(Problem).count() + 1000
        self.assertEqual(self.client.get(f"/problems/{missing}")[0], 404)
        self.assertEqual(self.client.get(f"/patterns/{missing}")[0], 404)
        self.assertEqual(self.client.get(f"/patterns/{missing}/problems")[0], 404)


if __name__ == "__main__":
    unittest.main()
