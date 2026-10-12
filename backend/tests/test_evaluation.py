import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pattern, PatternMastery, Problem, Submission, User
from app.routes.submissions import create_submission
from fastapi import HTTPException
from app.schemas.submission import SubmissionCreate
from app.services.evaluator import Evaluation, EvaluationError, EvaluationUnavailable, evaluate_submission
from app.services.feedback import generate_feedback


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.problem = type("Problem", (), {"test_cases": [
            {"input": "4\n", "expected_output": "4\n"},
        ]})()

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    @patch("app.services.evaluator._judge")
    def test_accepted_and_wrong_answer(self, judge):
        judge.return_value = {"status": {"id": 3}, "stdout": "4\n"}
        result = evaluate_submission(self.problem, "print(input())", "python")
        self.assertEqual(result.status, "Accepted")
        self.assertTrue(result.is_correct)
        judge.return_value = {"status": {"id": 3}, "stdout": "3\n"}
        result = evaluate_submission(self.problem, "print(3)", "python")
        self.assertEqual(result.status, "Wrong Answer")
        self.assertEqual(result.failed_test, 1)

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    @patch("app.services.evaluator._judge")
    def test_compilation_runtime_and_timeout(self, judge):
        for status_id, expected in ((6, "Compilation Error"), (11, "Runtime Error"), (5, "Time Limit Exceeded")):
            judge.return_value = {"status": {"id": status_id}, "stderr": "diagnostic"}
            result = evaluate_submission(self.problem, "code", "java")
            self.assertEqual(result.status, expected)

    def test_unsupported_language_and_missing_cases_are_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_submission(self.problem, "", "javascript")
        with patch.dict(os.environ, {"JUDGE0_URL": ""}):
            with self.assertRaises(EvaluationUnavailable):
                evaluate_submission(self.problem, "x", "python")
        with patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"}, clear=True):
            with self.assertRaises(EvaluationUnavailable):
                evaluate_submission(type("Problem", (), {"test_cases": []})(), "x", "python")

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid", "JUDGE0_API_KEY": "test-token"})
    @patch("app.services.evaluator.time.sleep")
    @patch("app.services.evaluator.urlopen")
    def test_wait_false_submission_is_polled_with_auth(self, open_url, _sleep):
        created = MagicMock()
        created.__enter__.return_value = created
        created.read.return_value = b'{"token":"submission-token"}'
        completed = MagicMock()
        completed.__enter__.return_value = completed
        completed.read.return_value = b'{"token":"submission-token","status":{"id":3,"description":"Accepted"},"stdout":"4\\n"}'
        open_url.side_effect = [created, completed]

        from app.services.evaluator import _judge
        result = _judge("print(input())", "python", "4\n", "https://judge.invalid")

        self.assertEqual(result["status"]["id"], 3)
        post, poll = [call.args[0] for call in open_url.call_args_list]
        self.assertEqual(post.full_url, "https://judge.invalid/submissions?base64_encoded=false&wait=false")
        self.assertEqual(post.get_method(), "POST")
        self.assertEqual(json.loads(post.data), {"source_code": "print(input())", "language_id": 71, "stdin": "4\n"})
        self.assertEqual(poll.full_url, "https://judge.invalid/submissions/submission-token?base64_encoded=false")
        self.assertEqual(poll.get_method(), "GET")
        self.assertEqual({key.lower(): value for key, value in post.header_items()}["x-auth-token"], "test-token")

    @patch.dict(os.environ, {"JUDGE0_TIMEOUT_SECONDS": "0.5"})
    @patch("app.services.evaluator.time.sleep")
    @patch("app.services.evaluator.time.monotonic", side_effect=[0, 0, 0, 1])
    @patch("app.services.evaluator.urlopen")
    def test_pending_poll_timeout_is_an_evaluation_error(self, open_url, _clock, _sleep):
        pending = MagicMock()
        pending.__enter__.return_value = pending
        pending.read.return_value = b'{"status":{"id":1,"description":"In Queue"}}'
        open_url.return_value = pending

        from app.services.evaluator import _poll
        with self.assertRaises(EvaluationError):
            _poll("https://judge.invalid", "submission-token", {})

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid", "JUDGE0_EVALUATION_TIMEOUT_SECONDS": "1"})
    @patch("app.services.evaluator.time.monotonic", side_effect=[0, 0, 2])
    @patch("app.services.evaluator._judge", return_value={"status": {"id": 3}, "stdout": "4"})
    def test_evaluation_deadline_is_shared_across_test_cases(self, judge, _clock):
        problem = type("Problem", (), {"test_cases": [
            {"input": "", "expected_output": "4"},
            {"input": "", "expected_output": "4"},
        ]})()
        with self.assertRaises(EvaluationError):
            evaluate_submission(problem, "code", "python")
        judge.assert_called_once()

    @patch.dict(os.environ, {"JUDGE0_TIMEOUT_SECONDS": "1"})
    @patch("app.services.evaluator.urlopen")
    def test_malformed_poll_response_is_an_evaluation_error(self, open_url):
        malformed = MagicMock()
        malformed.__enter__.return_value = malformed
        malformed.read.return_value = b'{"status":null}'
        open_url.return_value = malformed

        from app.services.evaluator import _poll
        with self.assertRaises(EvaluationError):
            _poll("https://judge.invalid", "submission-token", {})

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    @patch("app.services.evaluator._judge", side_effect=EvaluationError("offline"))
    def test_external_judge_failure_is_explicit(self, _judge):
        with self.assertRaises(EvaluationError):
            evaluate_submission(self.problem, "x", "python")


class FeedbackTests(unittest.TestCase):
    def test_rule_based_fallback_is_labeled(self):
        problem = type("Problem", (), {"title": "Demo", "description": "A demo"})()
        result = generate_feedback(problem, "x", "python", Evaluation("Wrong Answer", False, failed_test=2))
        self.assertEqual(result["provider"], "rule_based")
        self.assertIn("test 2", result["explanation"])

    @patch.dict(os.environ, {"AI_API_KEY": "mock", "AI_API_URL": "https://ai.invalid/v1", "AI_MODEL": "mock"})
    @patch("app.services.feedback._request_provider", return_value={"explanation": "evidence", "hint": "hint", "correction": "fix"})
    def test_mock_ai_provider(self, _provider):
        problem = type("Problem", (), {"title": "Demo", "description": "A demo"})()
        result = generate_feedback(problem, "x", "python", Evaluation("Wrong Answer", False))
        self.assertEqual(result["provider"], "ai")


class SubmissionFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        user = User(name="Test", email="evaluation@example.com")
        pattern = Pattern(name="Binary Search")
        self.session.add_all([user, pattern])
        self.session.flush()
        problem = Problem(title="Demo", platform="test", difficulty="Easy", pattern_id=pattern.id,
                          test_cases=[{"input": "", "expected_output": ""}])
        self.session.add(problem)
        self.session.commit()
        self.user_id, self.problem_id = user.id, problem.id

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    @patch("app.routes.submissions.recommend_problem", return_value=None)
    @patch("app.routes.submissions.evaluate_submission", return_value=Evaluation("Accepted", True))
    def test_server_verdict_drives_mastery_despite_spoofed_client_flags(self, _evaluate, _recommend):
        request = SubmissionCreate.model_validate({"user_id": self.user_id, "problem_id": self.problem_id,
                                                   "code": "solution", "language": "python",
                                                   "status": "Wrong Answer", "is_correct": False})
        result = create_submission(request, db=self.session)
        self.assertTrue(result["is_correct"])
        self.assertEqual(result["status"], "Accepted")
        self.assertEqual(result["mastery"]["total_attempts"], 1)
        self.assertEqual(result["mastery"]["correct_attempts"], 1)
        self.assertIsNone(result["mistake"])

    def test_missing_problem_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            create_submission(SubmissionCreate(user_id=self.user_id, problem_id=999,
                                               code="x", language="python"), db=self.session)
        self.assertEqual(error.exception.status_code, 404)

    def test_unsupported_language_is_rejected_without_recording(self):
        with self.assertRaises(HTTPException) as error:
            create_submission(SubmissionCreate(user_id=self.user_id, problem_id=self.problem_id,
                                               code="x", language="javascript"), db=self.session)
        self.assertEqual(error.exception.status_code, 422)

    @patch("app.routes.submissions.evaluate_submission", side_effect=EvaluationError("judge unavailable"))
    def test_judge_failure_is_reported_without_persisting_false_result(self, _evaluate):
        request = SubmissionCreate(user_id=self.user_id, problem_id=self.problem_id,
                                   code="solution", language="python")
        with self.assertRaises(HTTPException) as error:
            create_submission(request, db=self.session)
        self.assertEqual(error.exception.status_code, 502)
        self.assertEqual(self.session.query(Submission).count(), 0)
        self.assertEqual(self.session.query(PatternMastery).count(), 0)

