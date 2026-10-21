import io
import json
import os
import socket
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["CODEX_SKIP_DOTENV"] = "1"  # never load backend/.env (real keys, database)

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

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid", "JUDGE0_API_KEY": ""})
    @patch("app.services.evaluator.time.sleep")
    @patch("app.services.evaluator.urlopen")
    def test_user_agent_is_sent_on_submit_and_poll(self, open_url, _sleep):
        # Cloudflare-fronted judges reject urllib's default agent with HTTP 403.
        created = MagicMock()
        created.__enter__.return_value = created
        created.read.return_value = b'{"token":"t1"}'
        completed = MagicMock()
        completed.__enter__.return_value = completed
        completed.read.return_value = b'{"token":"t1","status":{"id":3},"stdout":"4\\n"}'
        open_url.side_effect = [created, completed]

        from app.services.evaluator import _judge
        _judge("print(input())", "python", "4\n", "https://judge.invalid")

        for request in (call.args[0] for call in open_url.call_args_list):
            headers = {key.lower(): value for key, value in request.header_items()}
            self.assertEqual(headers["user-agent"], "CodeX/1.0")

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

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    @patch("app.services.evaluator._judge")
    def test_output_comparison_ignores_trailing_whitespace_and_crlf(self, judge):
        for stdout in ("4", "4 \r\n", "4\n\n", "4\t\n"):
            judge.return_value = {"status": {"id": 3}, "stdout": stdout}
            self.assertTrue(evaluate_submission(self.problem, "code", "python").is_correct, repr(stdout))
        judge.return_value = {"status": {"id": 3}, "stdout": " 4\n"}
        self.assertEqual(evaluate_submission(self.problem, "code", "python").status, "Wrong Answer")
        judge.return_value = {"status": {"id": 3}, "stdout": None}
        self.assertEqual(evaluate_submission(self.problem, "code", "python").status, "Wrong Answer")

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    @patch("app.services.evaluator._judge")
    def test_all_runtime_error_statuses_map_to_runtime_error(self, judge):
        for status_id in (7, 8, 9, 10, 11, 12, 14):
            judge.return_value = {"status": {"id": status_id}, "stderr": None, "message": "signal"}
            result = evaluate_submission(self.problem, "code", "python")
            self.assertEqual(result.status, "Runtime Error")
            self.assertEqual(result.error, "signal")
            self.assertEqual(result.failed_test, 1)

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    @patch("app.services.evaluator._judge")
    def test_internal_and_unknown_judge_statuses_are_errors(self, judge):
        for payload in ({"status": {"id": 13}}, {"status": {"id": 99}}, {"status": "weird"}, {}):
            judge.return_value = payload
            with self.assertRaises(EvaluationError):
                evaluate_submission(self.problem, "code", "python")

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    @patch("app.services.evaluator._judge")
    def test_second_case_failure_reports_its_index(self, judge):
        problem = type("Problem", (), {"test_cases": [
            {"input": "1\n", "expected_output": "1\n"},
            {"input": "2\n", "expected_output": "2\n"},
        ]})()
        judge.side_effect = [{"status": {"id": 3}, "stdout": "1\n"}, {"status": {"id": 3}, "stdout": "0\n"}]
        result = evaluate_submission(problem, "code", "python")
        self.assertEqual((result.status, result.failed_test, result.actual_output), ("Wrong Answer", 2, "0"))

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    @patch("app.services.evaluator._judge")
    def test_invalid_test_cases_are_unavailable_not_verdicts(self, judge):
        for cases in ("not a list", [["input", "output"]], [{"input": 5, "expected_output": "5"}],
                      [{"input": "5\n"}], [{"input": "x", "expected_output": None}],
                      [{"input": "a" * 10_001, "expected_output": ""}],
                      [{"input": "", "expected_output": ""}] * 51):
            with self.subTest(cases=str(cases)[:40]):
                with self.assertRaises(EvaluationUnavailable):
                    evaluate_submission(type("Problem", (), {"test_cases": cases})(), "code", "python")
        judge.assert_not_called()

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    def test_oversized_source_is_rejected_before_contacting_judge(self):
        with patch("app.services.evaluator._judge") as judge:
            with self.assertRaises(ValueError):
                evaluate_submission(self.problem, "x" * 50_001, "python")
            judge.assert_not_called()

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    @patch("app.services.evaluator.time.sleep")
    @patch("app.services.evaluator.urlopen")
    def test_pending_status_in_create_response_is_polled(self, open_url, _sleep):
        queued = MagicMock()
        queued.__enter__.return_value = queued
        queued.read.return_value = b'{"token":"t1","status":{"id":1,"description":"In Queue"}}'
        processing = MagicMock()
        processing.__enter__.return_value = processing
        processing.read.return_value = b'{"token":"t1","status":{"id":2,"description":"Processing"}}'
        done = MagicMock()
        done.__enter__.return_value = done
        done.read.return_value = b'{"token":"t1","status":{"id":3},"stdout":"4\\n"}'
        open_url.side_effect = [queued, processing, done]

        from app.services.evaluator import _judge
        self.assertEqual(_judge("code", "python", "4\n", "https://judge.invalid")["status"]["id"], 3)
        self.assertEqual(open_url.call_count, 3)

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid", "JUDGE0_API_KEY": "sekret-token"})
    @patch("app.services.evaluator.urlopen")
    def test_http_errors_become_evaluation_errors_without_leaking_secrets(self, open_url):
        from urllib.error import HTTPError
        from app.services.evaluator import _judge
        for code, fragment in ((401, "credentials"), (403, "HTTP 403"), (429, "rate limit"), (500, "HTTP 500")):
            open_url.side_effect = HTTPError("https://judge.invalid", code, "nope", {}, None)
            with self.assertRaises(EvaluationError) as error:
                _judge("code", "python", "", "https://judge.invalid")
            self.assertIn(fragment, str(error.exception))
            self.assertNotIn("sekret-token", str(error.exception))
            if code == 403:
                self.assertNotIn("rejected the configured credentials", str(error.exception))

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid"})
    @patch("app.services.evaluator.urlopen")
    def test_non_object_create_response_is_malformed(self, open_url):
        from app.services.evaluator import _judge
        for body in (b"[]", b"null", b"not json"):
            malformed = MagicMock()
            malformed.__enter__.return_value = malformed
            malformed.read.return_value = body
            open_url.return_value = malformed
            with self.assertRaises(EvaluationError):
                _judge("code", "python", "", "https://judge.invalid")

    def test_auth_headers_follow_the_judge_host(self):
        from app.services.evaluator import _auth_headers
        with patch.dict(os.environ, {"JUDGE0_API_KEY": ""}):
            self.assertNotIn("X-Auth-Token", _auth_headers("https://judge.invalid"))
        with patch.dict(os.environ, {"JUDGE0_API_KEY": "secret", "JUDGE0_AUTH_HEADER": ""}):
            self.assertEqual(_auth_headers("https://ce.judge0.com")["X-Auth-Token"], "secret")
            rapid = _auth_headers("https://judge0-ce.p.rapidapi.com")
            self.assertEqual(rapid["X-RapidAPI-Key"], "secret")
            self.assertEqual(rapid["X-RapidAPI-Host"], "judge0-ce.p.rapidapi.com")
            self.assertNotIn("X-Auth-Token", rapid)
        with patch.dict(os.environ, {"JUDGE0_API_KEY": "secret", "JUDGE0_AUTH_HEADER": "X-Custom"}):
            self.assertEqual(_auth_headers("https://judge.invalid")["X-Custom"], "secret")

    @patch.dict(os.environ, {"JUDGE0_URL": "https://judge.invalid/  "})
    @patch("app.services.evaluator._judge", return_value={"status": {"id": 3}, "stdout": "4"})
    def test_judge_url_is_trimmed(self, judge):
        evaluate_submission(self.problem, "code", "python")
        self.assertEqual(judge.call_args.args[3], "https://judge.invalid")


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.problem = type("Problem", (), {
            "title": "Demo", "description": "Find the value", "test_cases": [
                {"input": "bad input", "expected_output": "expected", "visible": False},
            ],
        })()

    def test_rule_based_fallback_is_labeled(self):
        result = generate_feedback(self.problem, "x", "python", Evaluation("Wrong Answer", False, failed_test=2))
        self.assertEqual(result["provider"], "rule_based")
        self.assertIn("test 2", result["explanation"])

    @patch.dict(os.environ, {"AI_API_KEY": "mock", "AI_API_URL": "https://ai.invalid/v1", "AI_MODEL": "mock"})
    @patch("app.services.feedback._request_provider", return_value={"explanation": "evidence", "hint": "hint", "correction": "fix"})
    def test_mock_ai_provider_receives_execution_evidence(self, provider):
        evaluation = Evaluation("Wrong Answer", False, error="diagnostic", failed_test=1, actual_output="actual")
        result = generate_feedback(self.problem, "submitted code", "python", evaluation)
        self.assertEqual(result["provider"], "ai_generated")
        evidence = provider.call_args.args[0]
        self.assertEqual(evidence["problem"], "Demo")
        self.assertEqual(evidence["description"], "Find the value")
        self.assertEqual(evidence["code"], "submitted code")
        self.assertEqual(evidence["verdict"], "Wrong Answer")
        self.assertEqual(evidence["error"], "diagnostic")
        self.assertEqual(evidence["actual_output"], "actual")
        self.assertEqual(evidence["failed_case"], {"input": "bad input", "expected_output": "expected"})

    @patch.dict(os.environ, {}, clear=True)
    @patch("app.services.feedback._request_provider")
    def test_missing_configuration_uses_fallback_without_provider_call(self, provider):
        result = generate_feedback(self.problem, "x", "python", Evaluation("Accepted", True))
        self.assertEqual(result["provider"], "rule_based")
        provider.assert_not_called()

    @patch.dict(os.environ, {"AI_API_KEY": "mock", "AI_API_URL": "https://ai.invalid/v1"})
    @patch("app.services.feedback._request_provider", side_effect=ValueError("malformed"))
    def test_malformed_provider_response_uses_fallback(self, _provider):
        result = generate_feedback(self.problem, "x", "python", Evaluation("Wrong Answer", False, failed_test=1))
        self.assertEqual(result["provider"], "rule_based")

    @patch.dict(os.environ, {"AI_API_KEY": "mock", "AI_API_URL": "https://ai.invalid/v1"})
    @patch("app.services.feedback._request_provider", side_effect=TimeoutError("provider unavailable"))
    def test_provider_failure_uses_fallback(self, _provider):
        result = generate_feedback(self.problem, "x", "python", Evaluation("Runtime Error", False))
        self.assertEqual(result["provider"], "rule_based")
        self.assertIn("runtime error", result["explanation"])

    @patch.dict(os.environ, {"AI_API_KEY": "mock", "AI_API_URL": "https://ai.invalid/v1"})
    @patch("app.services.feedback.urlopen")
    def test_malformed_http_response_is_rejected(self, open_url):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"choices": []}'
        open_url.return_value = response
        from app.services.feedback import _request_provider
        with self.assertRaises((KeyError, IndexError, TypeError, ValueError)):
            _request_provider({"verdict": "Wrong Answer"})


def completion(content):
    """A mocked OpenAI-compatible chat completion response body."""
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]}).encode()
    return response


def provider_http_error(code, body):
    """A mocked provider HTTP error carrying an OpenAI-style JSON error body."""
    return HTTPError("https://ai.invalid", code, "error", {}, io.BytesIO(json.dumps(body).encode()))


VALID_FEEDBACK = json.dumps({"explanation": "Test 1 printed 0 instead of expected.",
                             "hint": "Look at the empty-input case.", "correction": "Return early when n is 0."})
AI_ENV = {"AI_API_KEY": "sk-test-secret", "AI_API_URL": "https://ai.invalid/v1", "AI_MODEL": "mock-model"}


@patch.dict(os.environ, AI_ENV)
@patch("app.services.feedback.urlopen")
class ProviderHttpTests(unittest.TestCase):
    """Mocked provider responses exercise real request building and parsing.
    They do not prove a live provider works."""

    def setUp(self):
        self.problem = type("Problem", (), {
            "title": "Demo", "description": "Find the value",
            "test_cases": [{"input": "bad input", "expected_output": "expected"}],
        })()
        self.wrong = Evaluation("Wrong Answer", False, error="diagnostic", failed_test=1, actual_output="0")

    def feedback(self, evaluation=None, code="submitted code"):
        return generate_feedback(self.problem, code, "python", evaluation or self.wrong)

    def assert_fallback(self, result):
        self.assertEqual(result["provider"], "rule_based")
        self.assertIn("test 1", result["explanation"])

    def test_successful_response_is_parsed_and_labelled(self, open_url):
        open_url.return_value = completion(VALID_FEEDBACK)
        result = self.feedback()
        self.assertEqual(result, {"explanation": "Test 1 printed 0 instead of expected.",
                                  "hint": "Look at the empty-input case.",
                                  "correction": "Return early when n is 0.", "provider": "ai_generated"})
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://ai.invalid/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-test-secret")
        self.assertEqual(request.get_header("User-agent"), "CodeX/1.0")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "mock-model")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertIn("max_tokens", body)
        self.assertIn("Judge0 verdict is authoritative", body["messages"][0]["content"])
        evidence = json.loads(body["messages"][1]["content"])
        self.assertEqual(evidence["verdict"], "Wrong Answer")
        self.assertEqual(evidence["error"], "diagnostic")
        self.assertEqual(evidence["failed_case"], {"input": "bad input", "expected_output": "expected"})

    def test_full_chat_completions_endpoint_is_not_doubled(self, open_url):
        open_url.return_value = completion(VALID_FEEDBACK)
        with patch.dict(os.environ, {"AI_API_URL": "https://ai.invalid/openai/v1/chat/completions/"}):
            self.feedback()
        self.assertEqual(open_url.call_args.args[0].full_url, "https://ai.invalid/openai/v1/chat/completions")

    def test_markdown_wrapped_json_is_accepted(self, open_url):
        open_url.return_value = completion(f"```json\n{VALID_FEEDBACK}\n```")
        self.assertEqual(self.feedback()["provider"], "ai_generated")

    def test_fields_are_trimmed_and_bounded(self, open_url):
        open_url.return_value = completion(json.dumps({"explanation": "  e" + "x" * 5000, "hint": "h" * 900,
                                                       "correction": "c"}))
        result = self.feedback()
        self.assertEqual(len(result["explanation"]), 1000)
        self.assertTrue(result["explanation"].startswith("e"))
        self.assertEqual(len(result["hint"]), 500)

    def test_code_and_diagnostics_sent_to_provider_are_bounded(self, open_url):
        open_url.return_value = completion(VALID_FEEDBACK)
        evaluation = Evaluation("Wrong Answer", False, error="e" * 9000, failed_test=1, actual_output="o" * 60000)
        self.feedback(evaluation, code="x" * 40000)
        evidence = json.loads(json.loads(open_url.call_args.args[0].data)["messages"][1]["content"])
        self.assertEqual(len(evidence["code"]), 12000)
        self.assertEqual(len(evidence["error"]), 2000)
        self.assertEqual(len(evidence["actual_output"]), 2000)

    def test_authentication_failures_fall_back_without_logging_the_key(self, open_url):
        for code, expected in ((401, "rejected the API key (HTTP 401)"), (403, "refused access")):
            with self.subTest(code=code):
                open_url.side_effect = HTTPError("https://ai.invalid", code, "denied", {}, None)
                with self.assertLogs("app.services.feedback", "WARNING") as logs:
                    self.assert_fallback(self.feedback())
                self.assertIn(expected, logs.output[0])
                self.assertNotIn("sk-test-secret", "".join(logs.output))

    def test_openai_invalid_key_body_is_reported_with_the_key_redacted(self, open_url):
        # Regression: the live OpenAI 401 reply echoes part of the rejected key.
        body = {"error": {"message": "Incorrect API key provided: sk-proj-****************************abcd. "
                                     "You can find your API key at https://platform.openai.com/account/api-keys.",
                          "type": "invalid_request_error", "param": None, "code": "invalid_api_key"}}
        open_url.side_effect = provider_http_error(401, body)
        with self.assertLogs("app.services.feedback", "WARNING") as logs:
            result = self.feedback()
        self.assert_fallback(result)
        reason = result["fallback_reason"]
        self.assertIn("rejected the API key (HTTP 401 invalid_api_key)", reason)
        self.assertIn("Incorrect API key provided: <redacted>", reason)
        for text in (reason, "".join(logs.output)):
            self.assertNotIn("sk-proj", text)
            self.assertNotIn("abcd", text)
            self.assertNotIn("sk-test-secret", text)

    def test_quota_rate_limit_and_model_errors_are_distinguished(self, open_url):
        cases = [
            (429, "insufficient_quota", "quota or credits exhausted"),
            # Regression: the live probe returned this code, which was mislabelled as a rate limit.
            (429, "credit_balance_exhausted", "quota or credits exhausted"),
            (429, "rate_limit_exceeded", "rate limit reached"),
            (404, "model_not_found", "model 'mock-model' was not found"),
            (400, "invalid_request_error", "provider rejected the request (HTTP 400"),
        ]
        for code, error_code, expected in cases:
            with self.subTest(error_code=error_code):
                open_url.side_effect = provider_http_error(code, {"error": {"code": error_code, "message": "details"}})
                with self.assertLogs("app.services.feedback", "WARNING"):
                    result = self.feedback()
                self.assert_fallback(result)
                self.assertIn(expected, result["fallback_reason"])
                self.assertIn(error_code, result["fallback_reason"])

    def test_network_failures_name_the_cause(self, open_url):
        cases = [
            (URLError(ConnectionRefusedError()), "could not reach the provider (ConnectionRefusedError)"),
            (URLError(TimeoutError()), "timed out"),
            (TimeoutError(), "timed out"),
        ]
        for error, expected in cases:
            with self.subTest(expected=expected):
                open_url.side_effect = error
                with self.assertLogs("app.services.feedback", "WARNING"):
                    self.assertIn(expected, self.feedback()["fallback_reason"])

    def test_successful_feedback_has_no_fallback_reason(self, open_url):
        open_url.return_value = completion(VALID_FEEDBACK)
        with self.assertLogs("app.services.feedback", "INFO") as logs:
            result = self.feedback()
        self.assertNotIn("fallback_reason", result)
        self.assertIn("AI feedback generated by mock-model", logs.output[0])

    def test_missing_configuration_reason_names_the_variable(self, open_url):
        with patch.dict(os.environ, {"AI_API_KEY": ""}), patch("app.services.feedback._disabled_warned", False):
            with self.assertLogs("app.services.feedback", "WARNING") as logs:
                first = self.feedback()
                second = self.feedback()
        self.assertEqual(first["fallback_reason"], "AI disabled: AI_API_KEY not set in the backend process")
        self.assertEqual(second["provider"], "rule_based")
        self.assertEqual(len(logs.output), 1, "the disabled warning is logged once, not per submission")
        open_url.assert_not_called()

    def test_configuration_report_never_contains_the_key(self, open_url):
        from app.services.feedback import ai_configuration
        with patch.dict(os.environ, {"AI_API_URL": "https://api.openai.com/v1/"}):
            report = ai_configuration()
        self.assertEqual(report["endpoint"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual((report["enabled"], report["key_configured"], report["model"]), (True, True, "mock-model"))
        self.assertNotIn("sk-test-secret", json.dumps(report))
        open_url.assert_not_called()

    def test_probe_reports_success_and_failure(self, open_url):
        # Tested directly: importing app.main would run startup DDL against
        # whatever DATABASE_URL the developer's shell points at.
        from app.services.feedback import probe_provider
        open_url.return_value = completion(VALID_FEEDBACK)
        self.assertEqual(probe_provider(), {"ok": True, "model": "mock-model", "reason": None})
        open_url.side_effect = provider_http_error(401, {"error": {"code": "invalid_api_key", "message": "bad"}})
        probe = probe_provider()
        self.assertFalse(probe["ok"])
        self.assertIn("invalid_api_key", probe["reason"])
        self.assertNotIn("sk-test-secret", json.dumps(probe))
        with patch.dict(os.environ, {"AI_API_URL": ""}):
            self.assertEqual(probe_provider(), {"ok": False, "reason": "AI disabled: AI_API_URL not set"})

    def test_rate_limit_and_server_errors_fall_back(self, open_url):
        for code in (429, 500, 503):
            with self.subTest(code=code):
                open_url.side_effect = HTTPError("https://ai.invalid", code, "error", {}, None)
                with self.assertLogs("app.services.feedback", "WARNING") as logs:
                    self.assert_fallback(self.feedback())
                self.assertIn(f"HTTP {code}", logs.output[0])

    def test_timeouts_and_network_errors_fall_back(self, open_url):
        for error in (TimeoutError("timed out"), URLError("unreachable"), socket.timeout("read timed out")):
            with self.subTest(error=type(error).__name__):
                open_url.side_effect = error
                with self.assertLogs("app.services.feedback", "WARNING"):
                    self.assert_fallback(self.feedback())

    def test_malformed_or_incomplete_content_falls_back(self, open_url):
        bad_contents = [
            "not json at all",
            "[1, 2, 3]",
            json.dumps({"explanation": "only one field"}),
            json.dumps({"explanation": "e", "hint": "  ", "correction": "c"}),
            json.dumps({"explanation": 5, "hint": "h", "correction": "c"}),
        ]
        for content in bad_contents:
            with self.subTest(content=content):
                open_url.return_value = completion(content)
                with self.assertLogs("app.services.feedback", "WARNING"):
                    self.assert_fallback(self.feedback())

    def test_empty_content_and_non_completion_bodies_fall_back(self, open_url):
        for content in ("", "   ", None):
            with self.subTest(content=content):
                open_url.return_value = completion(content)
                with self.assertLogs("app.services.feedback", "WARNING") as logs:
                    self.assert_fallback(self.feedback())
                self.assertIn("empty content", logs.output[0])
        for raw in (b"", b"<html>gateway</html>", b'{"error": {"message": "bad"}}', b'{"choices": []}'):
            with self.subTest(raw=raw):
                response = completion("")
                response.read.return_value = raw
                open_url.return_value = response
                with self.assertLogs("app.services.feedback", "WARNING"):
                    self.assert_fallback(self.feedback())

    def test_oversized_response_falls_back(self, open_url):
        response = completion("")
        response.read.return_value = b"x" * 64001
        open_url.return_value = response
        with self.assertLogs("app.services.feedback", "WARNING") as logs:
            self.assert_fallback(self.feedback())
        self.assertIn("size limit", logs.output[0])

    def test_feedback_contradicting_the_judge_verdict_is_rejected(self, open_url):
        open_url.return_value = completion(json.dumps({"verdict": "Accepted", "explanation": "Looks correct.",
                                                       "hint": "h", "correction": "c"}))
        with self.assertLogs("app.services.feedback", "WARNING") as logs:
            self.assert_fallback(self.feedback())
        self.assertIn("contradicted the Judge0 verdict", logs.output[0])

    def test_matching_verdict_echo_is_allowed(self, open_url):
        open_url.return_value = completion(json.dumps({"verdict": "wrong answer", "explanation": "e",
                                                       "hint": "h", "correction": "c"}))
        self.assertEqual(self.feedback()["provider"], "ai_generated")

    def test_blank_configuration_values_skip_the_provider(self, open_url):
        for overrides in ({"AI_API_KEY": "   "}, {"AI_API_URL": ""}):
            with self.subTest(overrides=overrides), patch.dict(os.environ, overrides):
                self.assert_fallback(self.feedback())
        open_url.assert_not_called()

    def test_invalid_timeout_setting_falls_back(self, open_url):
        with patch.dict(os.environ, {"AI_TIMEOUT_SECONDS": "soon"}), \
                self.assertLogs("app.services.feedback", "WARNING"):
            self.assert_fallback(self.feedback())


GEMINI_KEY = "AIzaFakeTestKey0123456789abcdefghijklm"
GEMINI_ENV = {"AI_API_KEY": GEMINI_KEY, "AI_API_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
              "AI_MODEL": "gemini-3.5-flash-lite"}


@patch.dict(os.environ, GEMINI_ENV)
@patch("app.services.feedback.urlopen")
class GeminiCompatibilityTests(unittest.TestCase):
    """Gemini's OpenAI-compatible endpoint, with its documented error shapes.
    Mocked: these do not prove a live Gemini key works."""

    def setUp(self):
        self.problem = type("Problem", (), {"title": "Demo", "description": "d",
                                            "test_cases": [{"input": "1", "expected_output": "1"}]})()

    def feedback(self):
        return generate_feedback(self.problem, "print(0)", "python", Evaluation("Wrong Answer", False, failed_test=1))

    def failure_reason(self, open_url, code, body):
        open_url.side_effect = provider_http_error(code, body)
        with self.assertLogs("app.services.feedback", "WARNING") as logs:
            result = self.feedback()
        self.assertEqual(result["provider"], "rule_based")
        self.assertNotIn(GEMINI_KEY, result["fallback_reason"] + "".join(logs.output))
        return result["fallback_reason"]

    def test_request_targets_the_gemini_openai_endpoint(self, open_url):
        open_url.return_value = completion(VALID_FEEDBACK)
        self.assertEqual(self.feedback()["provider"], "ai_generated")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {GEMINI_KEY}")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "gemini-3.5-flash-lite")
        self.assertEqual(body["max_tokens"], 700)
        self.assertNotIn("reasoning_effort", body, "only sent when configured; gpt-4o-mini rejects it")

    def test_token_limit_and_reasoning_effort_are_configurable(self, open_url):
        open_url.return_value = completion(VALID_FEEDBACK)
        with patch.dict(os.environ, {"AI_MAX_TOKENS": "2048", "AI_REASONING_EFFORT": "low"}):
            self.feedback()
        body = json.loads(open_url.call_args.args[0].data)
        self.assertEqual((body["max_tokens"], body["reasoning_effort"]), (2048, "low"))
        with patch.dict(os.environ, {"AI_MAX_TOKENS": "lots"}):
            self.feedback()
        self.assertEqual(json.loads(open_url.call_args.args[0].data)["max_tokens"], 700)

    def test_reply_cut_off_by_thinking_tokens_names_the_token_limit(self, open_url):
        for content in (None, '{"explanation": "The loop'):
            with self.subTest(content=content):
                response = completion(content)
                response.read.return_value = json.dumps({"choices": [{
                    "finish_reason": "length", "message": {"role": "assistant", "content": content}}]}).encode()
                open_url.return_value = response
                with self.assertLogs("app.services.feedback", "WARNING") as logs:
                    result = self.feedback()
                self.assertEqual(result["provider"], "rule_based")
                self.assertIn("AI_MAX_TOKENS limit", result["fallback_reason"])
                self.assertIn("AI_MAX_TOKENS", logs.output[0])

    def test_invalid_key_reported_as_http_400_is_a_key_error(self, open_url):
        body = [{"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.",
                           "status": "INVALID_ARGUMENT"}}]
        reason = self.failure_reason(open_url, 400, body)
        self.assertIn("rejected the API key (HTTP 400 INVALID_ARGUMENT)", reason)

    def test_free_tier_quota_is_reported_as_quota(self, open_url):
        body = [{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                           "message": "You exceeded your current quota. Quota exceeded for metric: "
                                      "generate_content_free_tier_requests, limit: 0"}}]
        reason = self.failure_reason(open_url, 429, body)
        self.assertIn("quota or credits exhausted (billing, plan or free-tier limit) (HTTP 429 RESOURCE_EXHAUSTED)", reason)
        self.assertIn("free_tier_requests", reason)

    def test_unknown_model_names_the_configured_model(self, open_url):
        body = {"error": {"code": 404, "status": "NOT_FOUND",
                          "message": "models/gemini-3.5-flash-lite is not found for API version v1beta"}}
        reason = self.failure_reason(open_url, 404, body)
        self.assertIn("model 'gemini-3.5-flash-lite' was not found", reason)
        self.assertIn("HTTP 404 NOT_FOUND", reason)

    def test_gemini_key_echoed_in_an_error_is_redacted(self, open_url):
        body = {"error": {"code": 403, "status": "PERMISSION_DENIED",
                          "message": f"Requests from key {GEMINI_KEY[:20]} are blocked."}}
        reason = self.failure_reason(open_url, 403, body)
        self.assertIn("refused access", reason)
        self.assertNotIn(GEMINI_KEY[:20], reason)


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

