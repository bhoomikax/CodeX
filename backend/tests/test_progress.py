import os
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pattern, PatternMastery, Problem, Submission, User
from app.routes.progress import get_progress, router


class ProgressRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.alice = User(name="Alice", email="progress-alice@example.com")
        self.bob = User(name="Bob", email="progress-bob@example.com")
        self.arrays = Pattern(name="Arrays")
        self.graphs = Pattern(name="Graphs")
        self.session.add_all([self.alice, self.bob, self.arrays, self.graphs])
        self.session.flush()

        self.array_problem = self._add_problem("Array Sum", self.arrays)
        self.graph_problem = self._add_problem("Graph Walk", self.graphs)
        self.session.add_all(
            [
                PatternMastery(
                    user_id=self.alice.id,
                    pattern_id=self.arrays.id,
                    mastery_score=40,
                    confidence_score=36,
                    retention_score=40,
                    total_attempts=2,
                    correct_attempts=1,
                    consecutive_correct=0,
                ),
                PatternMastery(
                    user_id=self.alice.id,
                    pattern_id=self.graphs.id,
                    mastery_score=75,
                    confidence_score=67.5,
                    retention_score=75,
                    total_attempts=1,
                    correct_attempts=1,
                    consecutive_correct=1,
                ),
                PatternMastery(
                    user_id=self.bob.id,
                    pattern_id=self.arrays.id,
                    mastery_score=99,
                    confidence_score=99,
                    retention_score=99,
                    total_attempts=1,
                    correct_attempts=1,
                    consecutive_correct=1,
                ),
            ]
        )
        self.session.flush()

        now = datetime(2026, 10, 12, 12, 0, 0)
        self._add_submission(self.alice, self.array_problem, True, now - timedelta(minutes=3))
        self._add_submission(self.alice, self.array_problem, False, now - timedelta(minutes=2))
        self._add_submission(self.alice, self.graph_problem, True, now - timedelta(minutes=1))
        self._add_submission(self.bob, self.array_problem, True, now)
        self.session.commit()

        app = FastAPI()
        app.include_router(router)
        self.app = app

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _add_problem(self, title, pattern):
        problem = Problem(
            title=title,
            platform="Test",
            difficulty="Easy",
            pattern_id=pattern.id,
            test_cases=[],
        )
        self.session.add(problem)
        self.session.flush()
        return problem

    def _add_submission(self, user, problem, is_correct, submitted_at):
        self.session.add(
            Submission(
                user_id=user.id,
                problem_id=problem.id,
                language="python",
                status="Accepted" if is_correct else "Wrong Answer",
                is_correct=is_correct,
                submitted_at=submitted_at,
            )
        )

    def test_progress_calculates_accuracy_and_pattern_mastery_per_user(self):
        progress = get_progress(user_id=self.alice.id, db=self.session).model_dump()

        self.assertEqual(progress["total_attempts"], 3)
        self.assertEqual(progress["correct_attempts"], 2)
        self.assertEqual(progress["accuracy_percentage"], 66.67)
        self.assertEqual(
            [(item["pattern_name"], item["total_attempts"], item["correct_attempts"])
             for item in progress["patterns"]],
            [("Arrays", 2, 1), ("Graphs", 1, 1)],
        )
        self.assertEqual(progress["patterns"][0]["accuracy_percentage"], 50.0)
        self.assertEqual(progress["strongest_pattern"]["pattern_name"], "Graphs")
        self.assertEqual(progress["weakest_pattern"]["pattern_name"], "Arrays")
        self.assertEqual(len(progress["recent_submissions"]), 3)
        self.assertEqual(
            [submission["problem_title"] for submission in progress["recent_submissions"]],
            ["Graph Walk", "Array Sum", "Array Sum"],
        )
        self.assertNotIn("code", progress["recent_submissions"][0])

    def test_empty_learner_progress_uses_empty_values(self):
        charlie = User(name="Charlie", email="progress-charlie@example.com")
        self.session.add(charlie)
        self.session.commit()

        progress = get_progress(user_id=charlie.id, db=self.session)

        self.assertEqual(progress.total_attempts, 0)
        self.assertEqual(progress.correct_attempts, 0)
        self.assertEqual(progress.accuracy_percentage, 0.0)
        self.assertEqual(progress.patterns, [])
        self.assertIsNone(progress.strongest_pattern)
        self.assertIsNone(progress.weakest_pattern)
        self.assertEqual(progress.recent_submissions, [])

    def test_missing_user_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            get_progress(user_id=99999, db=self.session)

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "User not found")

    def test_nonpositive_user_id_is_rejected(self):
        parameter = self.app.openapi()["paths"]["/progress/"]["get"]["parameters"][0]
        self.assertEqual(parameter["name"], "user_id")
        self.assertTrue(parameter["required"])
        self.assertEqual(parameter["schema"]["exclusiveMinimum"], 0)
