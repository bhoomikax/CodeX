"""Submission flow, transaction safety and per-user scoping of the API routes."""
import json
import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["CODEX_SKIP_DOTENV"] = "1"  # never load backend/.env (real keys, database)

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Mistake, Pattern, PatternMastery, Problem, Submission, User
from app.routes.mastery import get_mastery
from app.routes.mistakes import get_mistakes
from app.routes.submissions import create_submission, get_submissions
from app.schemas.problem import ProblemResponse
from app.schemas.submission import SubmissionCreate
from app.services.evaluator import Evaluation, EvaluationUnavailable
from app.services.recommendation import recommend_problem


class RouteTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.alice = User(name="Alice", email="alice@example.com")
        self.bob = User(name="Bob", email="bob@example.com")
        pattern = Pattern(name="Two Pointers")
        self.session.add_all([self.alice, self.bob, pattern])
        self.session.flush()
        self.problem = Problem(
            title="Demo", platform="test", difficulty="Easy", pattern_id=pattern.id,
            test_cases=[
                {"input": "1\n", "expected_output": "1\n", "visible": True},
                {"input": "2\n", "expected_output": "2\n", "visible": False},
            ],
        )
        self.session.add(self.problem)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def submit(self, user, evaluation):
        with patch("app.routes.submissions.evaluate_submission", return_value=evaluation), \
                patch("app.routes.submissions.recommend_problem", return_value=None):
            return create_submission(
                SubmissionCreate(user_id=user.id, problem_id=self.problem.id, code="code", language="Python"),
                db=self.session,
            )


class TransactionSafetyTests(RouteTestCase):
    @patch("app.routes.submissions.update_mastery", side_effect=SQLAlchemyError("disk full"))
    def test_persistence_failure_rolls_back_everything(self, _mastery):
        with self.assertRaises(HTTPException) as error:
            self.submit(self.alice, Evaluation("Wrong Answer", False, failed_test=1))
        self.assertEqual(error.exception.status_code, 500)
        self.assertEqual(self.session.query(Submission).count(), 0)
        self.assertEqual(self.session.query(Mistake).count(), 0)
        self.assertEqual(self.session.query(PatternMastery).count(), 0)

    @patch("app.routes.submissions.create_mistake", side_effect=RuntimeError("unexpected"))
    def test_unexpected_failure_after_flush_rolls_back(self, _mistake):
        with self.assertRaises(HTTPException) as error:
            self.submit(self.alice, Evaluation("Runtime Error", False, failed_test=1))
        self.assertEqual(error.exception.status_code, 500)
        self.assertEqual(self.session.query(Submission).count(), 0)
        self.assertEqual(self.session.query(PatternMastery).count(), 0)

    def test_unavailable_judge_returns_503_without_persisting(self):
        with patch("app.routes.submissions.evaluate_submission",
                   side_effect=EvaluationUnavailable("configure JUDGE0_URL")):
            with self.assertRaises(HTTPException) as error:
                create_submission(
                    SubmissionCreate(user_id=self.alice.id, problem_id=self.problem.id, code="x", language="python"),
                    db=self.session,
                )
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.session.query(Submission).count(), 0)

    def test_missing_user_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            create_submission(SubmissionCreate(user_id=999, problem_id=self.problem.id, code="x", language="python"),
                              db=self.session)
        self.assertEqual(error.exception.status_code, 404)

    @patch.dict(os.environ, {"AI_API_KEY": "mock", "AI_API_URL": "https://ai.invalid/v1"})
    @patch("app.services.feedback._request_provider", side_effect=TimeoutError("provider down"))
    def test_ai_failure_keeps_verdict_and_falls_back(self, _provider):
        result = self.submit(self.alice, Evaluation("Accepted", True))
        self.assertTrue(result["is_correct"])
        self.assertEqual(result["status"], "Accepted")
        self.assertEqual(result["evaluation_details"]["feedback"]["provider"], "rule_based")
        self.assertIsNone(result["mistake"])

    @patch("app.routes.submissions.generate_feedback", return_value={
        "provider": "ai_generated", "explanation": "This is Accepted.", "hint": "hint", "correction": "fix",
    })
    def test_ai_claim_cannot_override_incorrect_verdict_or_learning_records(self, _feedback):
        result = self.submit(self.alice, Evaluation("Wrong Answer", False, failed_test=1))
        self.assertFalse(result["is_correct"])
        self.assertEqual(result["status"], "Wrong Answer")
        self.assertEqual(result["evaluation_details"]["feedback"]["provider"], "ai_generated")
        self.assertEqual(result["mastery"]["correct_attempts"], 0)
        self.assertEqual(result["mastery"]["total_attempts"], 1)
        self.assertEqual(result["mistake"]["category"], "edge_case")
        self.assertEqual(result["mistake"]["explanation"], "This is Accepted.")
        self.assertEqual(self.session.query(Submission).count(), 1)

    @patch.dict(os.environ, {"AI_API_KEY": "mock", "AI_API_URL": "https://ai.invalid/v1"})
    @patch("app.services.feedback.urlopen")
    def test_ai_feedback_label_is_returned_and_persisted(self, open_url):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({"choices": [{"message": {"content": json.dumps(
            {"explanation": "AI says the loop stops early.", "hint": "h", "correction": "c"})}}]}).encode()
        open_url.return_value = response
        result = self.submit(self.alice, Evaluation("Wrong Answer", False, failed_test=2, actual_output="1"))
        self.assertEqual(result["status"], "Wrong Answer")
        self.assertFalse(result["is_correct"])
        self.assertEqual(result["evaluation_details"]["feedback"]["provider"], "ai_generated")
        self.assertEqual(result["mistake"]["explanation"], "AI says the loop stops early.")
        saved = get_submissions(user_id=self.alice.id, db=self.session)[0]
        self.assertEqual(saved.evaluation_details["feedback"]["provider"], "ai_generated")

    @patch.dict(os.environ, {"AI_API_KEY": "sk-route-secret", "AI_API_URL": "https://ai.invalid/v1"})
    @patch("app.services.feedback.urlopen", side_effect=HTTPError("https://ai.invalid", 401, "denied", {}, None))
    def test_provider_failure_still_saves_every_learning_record(self, _open_url):
        with patch("app.routes.submissions.evaluate_submission",
                   return_value=Evaluation("Wrong Answer", False, failed_test=1, actual_output="0")), \
                patch("app.routes.submissions.recommend_problem", wraps=recommend_problem) as recommend, \
                self.assertLogs("app.services.feedback", "WARNING"):
            result = create_submission(
                SubmissionCreate(user_id=self.alice.id, problem_id=self.problem.id, code="code", language="python"),
                db=self.session,
            )
        recommend.assert_called_once()
        self.assertEqual(result["status"], "Wrong Answer")
        self.assertEqual(result["evaluation_details"]["feedback"]["provider"], "rule_based")
        self.assertEqual(self.session.query(Submission).count(), 1)
        self.assertEqual(self.session.query(Mistake).count(), 1)
        mastery = self.session.query(PatternMastery).one()
        self.assertEqual((mastery.total_attempts, mastery.correct_attempts), (1, 0))
        self.assertIn("test 1", self.session.query(Mistake).one().explanation)
        # The sanitized reason reaches the API response and the saved row.
        reason = result["evaluation_details"]["feedback"]["fallback_reason"]
        self.assertIn("rejected the API key (HTTP 401)", reason)
        saved = self.session.query(Submission).one().evaluation_details["feedback"]
        self.assertEqual(saved["fallback_reason"], reason)
        self.assertNotIn("sk-route-secret", json.dumps(result, default=str))

    def test_language_is_normalised_when_saved(self):
        result = self.submit(self.alice, Evaluation("Accepted", True))
        self.assertEqual(result["language"], "python")


class MistakeAndMasteryTests(RouteTestCase):
    def test_mistake_category_follows_verdict(self):
        expectations = {
            "Compilation Error": "syntax_error",
            "Wrong Answer": "edge_case",
            "Runtime Error": "logic_error",
            "Time Limit Exceeded": "inefficient_solution",
        }
        for status, category in expectations.items():
            with self.subTest(status=status):
                result = self.submit(self.alice, Evaluation(status, False, failed_test=1, error="details"))
                self.assertEqual(result["mistake"]["category"], category)
                self.assertEqual(result["mistake"]["submission_id"], result["id"])
        self.assertEqual(self.session.query(Mistake).count(), 4)

    def test_streak_counts_and_resets(self):
        for _ in range(3):
            result = self.submit(self.alice, Evaluation("Accepted", True))
        self.assertEqual(result["mastery"]["consecutive_correct"], 3)
        self.assertEqual(result["mastery"]["correct_attempts"], 3)
        self.assertEqual(result["mastery"]["total_attempts"], 3)

        result = self.submit(self.alice, Evaluation("Wrong Answer", False, failed_test=2))
        self.assertEqual(result["mastery"]["consecutive_correct"], 0)
        self.assertEqual(result["mastery"]["correct_attempts"], 3)
        self.assertEqual(result["mastery"]["total_attempts"], 4)
        self.assertEqual(self.session.query(PatternMastery).count(), 1)

    def test_correct_submission_creates_no_mistake(self):
        self.submit(self.alice, Evaluation("Accepted", True))
        self.assertEqual(self.session.query(Mistake).count(), 0)


class UserScopingTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.submit(self.alice, Evaluation("Accepted", True))
        self.submit(self.bob, Evaluation("Wrong Answer", False, failed_test=1))

    def test_submissions_can_be_scoped_to_a_user(self):
        self.assertEqual(len(get_submissions(user_id=None, db=self.session)), 2)
        bob_only = get_submissions(user_id=self.bob.id, db=self.session)
        self.assertEqual([s.user_id for s in bob_only], [self.bob.id])

    def test_mastery_can_be_scoped_to_a_user(self):
        self.assertEqual(len(get_mastery(user_id=None, db=self.session)), 2)
        alice_only = get_mastery(user_id=self.alice.id, db=self.session)
        self.assertEqual([m.user_id for m in alice_only], [self.alice.id])

    def test_mistakes_can_be_scoped_to_a_user(self):
        self.assertEqual(len(get_mistakes(user_id=None, db=self.session)), 1)
        self.assertEqual(len(get_mistakes(user_id=self.alice.id, db=self.session)), 0)
        self.assertEqual(len(get_mistakes(user_id=self.bob.id, db=self.session)), 1)

    def test_mastery_is_tracked_per_user(self):
        alice = self.session.query(PatternMastery).filter_by(user_id=self.alice.id).one()
        bob = self.session.query(PatternMastery).filter_by(user_id=self.bob.id).one()
        self.assertEqual((alice.correct_attempts, bob.correct_attempts), (1, 0))


class ProblemExposureTests(RouteTestCase):
    def test_only_visible_cases_are_exposed(self):
        payload = ProblemResponse.model_validate(self.problem).model_dump()
        self.assertTrue(payload["test_cases_available"])
        self.assertEqual(payload["sample_cases"], [{"input": "1\n", "expected_output": "1\n"}])
        self.assertNotIn("test_cases", payload)

    def test_malformed_cases_are_reported_as_unavailable(self):
        self.problem.test_cases = [{"input": 5}]
        self.assertFalse(self.problem.test_cases_available)
        self.assertEqual(self.problem.sample_cases, [])
