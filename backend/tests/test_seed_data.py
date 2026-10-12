import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import seed
from app.database import Base
from app.models import Pattern, Problem
from app.services.evaluator import validate_test_cases
from tests.reference_solutions import REFERENCE_SOLUTIONS


def load_json(name):
    with open(seed.DATA_DIR / name, "r", encoding="utf-8") as file:
        return json.load(file)


class TestCaseDataTests(unittest.TestCase):
    """data/test_cases.json must be well-formed and provably correct."""

    @classmethod
    def setUpClass(cls):
        cls.cases = load_json("test_cases.json")
        cls.problem_ids = {item["external_id"] for item in load_json("problems.json")}

    def test_every_entry_belongs_to_a_seeded_problem(self):
        self.assertTrue(self.cases)
        for external_id in self.cases:
            self.assertIn(external_id, self.problem_ids)

    def test_every_entry_is_accepted_by_the_evaluator(self):
        for external_id, entry in self.cases.items():
            with self.subTest(problem=external_id):
                self.assertTrue(entry.get("description"))
                validated = validate_test_cases(entry["test_cases"])
                self.assertEqual(len(validated), len(entry["test_cases"]))
                for case in entry["test_cases"]:
                    self.assertIsInstance(case["visible"], bool)
                self.assertTrue(any(case["visible"] for case in entry["test_cases"]),
                                "each problem needs at least one visible sample case")

    def test_expected_outputs_match_reference_solutions(self):
        for external_id, entry in self.cases.items():
            solve = REFERENCE_SOLUTIONS[external_id]
            for case in entry["test_cases"]:
                with self.subTest(problem=external_id, stdin=case["input"]):
                    self.assertEqual(solve(case["input"]), case["expected_output"])

    def test_binary_search_demo_cases_are_unchanged(self):
        self.assertEqual(
            [case["input"] for case in self.cases["704"]["test_cases"]],
            ["6\n-1 0 3 5 9 12\n9\n", "6\n-1 0 3 5 9 12\n2\n", "1\n5\n5\n"],
        )


class SeedBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _seed(self):
        pattern_map = seed.seed_patterns(self.session)
        result = seed.seed_problems(self.session, pattern_map)
        self.session.commit()
        return result

    def test_seed_is_idempotent(self):
        created, updated = self._seed()
        self.assertEqual(created, len(load_json("problems.json")))
        self.assertEqual(updated, 0)
        patterns, problems = self.session.query(Pattern).count(), self.session.query(Problem).count()

        self.assertEqual(self._seed(), (0, 0))
        self.assertEqual(self.session.query(Pattern).count(), patterns)
        self.assertEqual(self.session.query(Problem).count(), problems)

    def test_seed_attaches_verified_test_cases(self):
        self._seed()
        evaluable = [p for p in self.session.query(Problem).all() if p.test_cases_available]
        self.assertEqual(len(evaluable), len(load_json("test_cases.json")))
        demo = self.session.query(Problem).filter_by(external_id="704").one()
        self.assertEqual(len(demo.test_cases), 3)
        self.assertIn("Console I/O", demo.description)

    def test_seed_fills_cases_for_existing_problem_without_them(self):
        pattern = Pattern(name="Binary Search")
        self.session.add(pattern)
        self.session.flush()
        self.session.add(Problem(title="Binary Search", platform="LeetCode", external_id="704",
                                 difficulty="Easy", pattern_id=pattern.id, test_cases=[]))
        self.session.commit()

        created, updated = self._seed()
        self.assertEqual(updated, 1)
        self.assertEqual(created, len(load_json("problems.json")) - 1)
        demo = self.session.query(Problem).filter_by(external_id="704").one()
        self.assertEqual(len(demo.test_cases), 3)

    def test_seed_never_overwrites_hand_configured_cases(self):
        pattern = Pattern(name="Binary Search")
        self.session.add(pattern)
        self.session.flush()
        custom = [{"input": "1\n1\n1\n", "expected_output": "0\n", "visible": True}]
        self.session.add(Problem(title="Binary Search", platform="LeetCode", external_id="704",
                                 difficulty="Easy", pattern_id=pattern.id, test_cases=custom,
                                 description="custom"))
        self.session.commit()

        self._seed()
        demo = self.session.query(Problem).filter_by(external_id="704").one()
        self.assertEqual(demo.test_cases, custom)
        self.assertEqual(demo.description, "custom")

    @patch("app.seed.SessionLocal")
    @patch("app.seed.DATABASE_URL", "postgresql://user:secret@db.example:5433/codex")
    def test_non_sqlite_target_requires_confirm(self, session_factory):
        self.assertEqual(seed.main([]), 1)
        session_factory.assert_not_called()

    def test_database_description_hides_credentials(self):
        text = seed.describe_database("postgresql://user:secret@db.example:5433/codex")
        self.assertNotIn("secret", text)
        self.assertIn("codex", text)
        self.assertTrue(seed.is_sqlite("sqlite:///./demo.sqlite3"))
        self.assertFalse(seed.is_sqlite("postgresql://x"))
