"""Cross-module learner journey using isolated SQLite and mocked providers."""
import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Mistake, Pattern, PatternMastery, Problem, Submission, User
from app.routes.problems import get_problems
from app.routes.progress import get_progress
from app.routes.recommendations import get_recommendation
from app.routes.revisions import get_revisions
from app.routes.submissions import create_submission
from app.schemas.problem import ProblemResponse
from app.schemas.submission import SubmissionCreate
from app.services.evaluator import Evaluation


class LearningJourneyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.learner = User(name="Journey Learner", email="journey@example.com")
        self.pattern = Pattern(name="Two Pointers")
        self.session.add_all([self.learner, self.pattern])
        self.session.flush()

        self.problems = [
            self._add_problem("Pair Match Easy", "Easy"),
            self._add_problem("Pair Match Medium", "Medium"),
            self._add_problem("Pair Match Follow-up", "Easy"),
        ]
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _add_problem(self, title, difficulty):
        problem = Problem(
            title=title,
            platform="Test",
            difficulty=difficulty,
            pattern_id=self.pattern.id,
            description=f"Test problem: {title}",
            test_cases=[
                {"input": "1 2", "expected_output": "3", "visible": True}
            ],
        )
        self.session.add(problem)
        self.session.flush()
        return problem

    def _submit(self, problem, evaluation):
        feedback = {
            "explanation": f"Mock feedback for {evaluation.status}.",
            "hint": "Review the test case.",
            "correction": "Check the boundary condition.",
            "provider": "test",
        }
        with (
            patch(
                "app.routes.submissions.evaluate_submission",
                return_value=evaluation,
            ) as evaluate,
            patch(
                "app.routes.submissions.generate_feedback",
                return_value=feedback,
            ),
        ):
            result = create_submission(
                SubmissionCreate(
                    user_id=self.learner.id,
                    problem_id=problem.id,
                    code="print(3)",
                    language="Python",
                ),
                db=self.session,
            )
        evaluate.assert_called_once()
        return result

    def test_problem_submission_progress_recommendation_and_revision_journey(self):
        # 1. Catalog API exposes only public sample cases and evaluation readiness.
        catalog = [
            ProblemResponse.model_validate(problem)
            for problem in get_problems(db=self.session)
        ]
        self.assertEqual(len(catalog), len(self.problems))
        self.assertTrue(all(problem.test_cases_available for problem in catalog))
        self.assertEqual(
            [sample.model_dump() for sample in catalog[0].sample_cases],
            [{"input": "1 2", "expected_output": "3"}],
        )

        # 2-4. Verdicts come from a mocked judge, but the real submission route
        # persists submissions, updates mastery, creates mistakes and recommends.
        incorrect = self._submit(
            self.problems[0],
            Evaluation("Wrong Answer", False, failed_test=1),
        )
        self.assertFalse(incorrect["is_correct"])
        self.assertEqual(incorrect["mistake"]["category"], "edge_case")
        self.assertEqual(incorrect["mastery"]["total_attempts"], 1)
        self.assertEqual(incorrect["mastery"]["correct_attempts"], 0)
        self.assertEqual(incorrect["recommendation"]["problem_id"], self.problems[2].id)
        self.assertEqual(
            self.session.query(Mistake).filter_by(submission_id=incorrect["id"]).count(),
            1,
        )

        correct = self._submit(
            self.problems[1],
            Evaluation("Accepted", True),
        )
        self.assertTrue(correct["is_correct"])
        self.assertIsNone(correct["mistake"])
        self.assertEqual(correct["mastery"]["total_attempts"], 2)
        self.assertEqual(correct["mastery"]["correct_attempts"], 1)
        self.assertEqual(correct["recommendation"]["problem_id"], self.problems[2].id)
        self.assertEqual(self.session.query(Submission).count(), 2)
        self.assertEqual(self.session.query(Mistake).count(), 1)

        # 5. Analytics reflect both persisted verdicts and their outcomes.
        progress = get_progress(user_id=self.learner.id, db=self.session)
        self.assertEqual(progress.total_attempts, 2)
        self.assertEqual(progress.correct_attempts, 1)
        self.assertEqual(progress.accuracy_percentage, 50.0)
        self.assertEqual(progress.patterns[0].total_attempts, 2)
        self.assertEqual(progress.patterns[0].correct_attempts, 1)
        self.assertEqual(len(progress.recent_submissions), 2)

        # 6. Recommendation API uses the now-persisted mastery and attempt history.
        recommendation = get_recommendation(
            user_id=self.learner.id,
            db=self.session,
        )
        self.assertEqual(recommendation.problem_id, self.problems[2].id)
        self.assertEqual(recommendation.pattern, self.pattern.name)
        self.assertTrue(recommendation.reason)

        # 7. Make the persisted revision date due, then consume the real route.
        mastery = (
            self.session.query(PatternMastery)
            .filter_by(user_id=self.learner.id, pattern_id=self.pattern.id)
            .one()
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        mastery.next_revision_at = now - timedelta(minutes=1)
        self.session.commit()
        revisions = get_revisions(user_id=self.learner.id, db=self.session)
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].pattern_id, self.pattern.id)
        self.assertIn(
            revisions[0].problem_id,
            {problem.id for problem in self.problems},
        )
        self.assertTrue(revisions[0].due_at <= now)
        self.assertTrue(revisions[0].reason)

        # The recommendation and revision pages link to the same practice route
        # using these API-provided IDs; neither path requires changing evaluation.
        self.assertGreater(recommendation.problem_id, 0)
        self.assertGreater(revisions[0].problem_id, 0)
