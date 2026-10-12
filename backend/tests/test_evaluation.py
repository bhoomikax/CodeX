import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pattern, Problem, User
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
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(EvaluationUnavailable):
                evaluate_submission(type("Problem", (), {"test_cases": []})(), "x", "python")

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
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine)()
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

