"""Judge0-backed evaluation. Submitted code is only sent to the configured sandbox."""
import json
import os
import time
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


LANGUAGES = {"python": 71, "java": 62}
MAX_CODE_BYTES = 50_000
MAX_INPUT_BYTES = 10_000
MAX_OUTPUT_BYTES = 50_000
MAX_TEST_CASES = 50


@dataclass
class Evaluation:
    status: str
    is_correct: bool
    error: str | None = None
    failed_test: int | None = None
    actual_output: str | None = None

    def as_dict(self):
        return asdict(self)


class EvaluationUnavailable(Exception):
    pass


class EvaluationError(Exception):
    pass


def evaluate_submission(problem, source_code: str, language: str) -> Evaluation:
    language = language.strip().lower()
    if language not in LANGUAGES:
        raise ValueError("Supported languages are python and java")
    if len(source_code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ValueError("Source code exceeds the 50000 byte limit")
    cases = problem.test_cases or []
    if not cases:
        raise EvaluationUnavailable("Evaluation is unavailable: this problem has no configured test cases")
    if len(cases) > MAX_TEST_CASES:
        raise EvaluationError("This problem exceeds the configured test case limit")
    base_url = os.getenv("JUDGE0_URL", "").rstrip("/")
    if not base_url:
        raise EvaluationUnavailable("Evaluation is unavailable: configure JUDGE0_URL")

    deadline = time.monotonic() + float(os.getenv("JUDGE0_EVALUATION_TIMEOUT_SECONDS", "35"))
    for index, case in enumerate(cases, start=1):
        if time.monotonic() >= deadline:
            raise EvaluationError("The evaluation exceeded its overall time limit")
        input_data = case.get("input", "")
        expected = case.get("expected_output", "")
        if len(str(input_data).encode("utf-8")) > MAX_INPUT_BYTES:
            raise EvaluationError("Configured test input exceeds the judge limit")
        result = _judge(source_code, language, str(input_data), base_url, deadline=deadline)
        status_data = result.get("status") if isinstance(result, dict) else None
        status = status_data.get("id") if isinstance(status_data, dict) else None
        if status in (3, 4):
            actual = (result.get("stdout") or "").strip()
            if status == 4 or actual != str(expected).strip():
                return Evaluation("Wrong Answer", False, failed_test=index,
                                  actual_output=actual[:MAX_OUTPUT_BYTES])
            continue
        if status == 5:
            return Evaluation("Time Limit Exceeded", False, error="The program exceeded the judge time limit.", failed_test=index)
        if status == 6:
            return Evaluation("Compilation Error", False, error=_safe_text(result.get("compile_output")), failed_test=index)
        if status in (7, 8, 9, 10, 11, 12, 14):
            return Evaluation("Runtime Error", False, error=_safe_text(result.get("stderr") or result.get("message")), failed_test=index)
        if status == 13:
            raise EvaluationError("The judge reported an internal execution error")
        raise EvaluationError("The judge returned an unsupported or unsuccessful status")
    return Evaluation("Accepted", True)


def _judge(code, language, input_data, base_url, deadline=None):
    token = os.getenv("JUDGE0_API_KEY")
    payload = {"source_code": code, "language_id": LANGUAGES[language], "stdin": input_data}
    url = f"{base_url}/submissions?base64_encoded=false&wait=false"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["X-Auth-Token"] = token
    request = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        timeout = float(os.getenv("JUDGE0_TIMEOUT_SECONDS", "15"))
        if deadline is not None:
            timeout = min(timeout, max(0.1, deadline - time.monotonic()))
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read(MAX_OUTPUT_BYTES + 1))
        if not isinstance(result, dict):
            raise EvaluationError("The judge returned a malformed response")
        if result.get("token") and not result.get("status"):
            return _poll(base_url, result["token"], headers, deadline=deadline)
        return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise EvaluationError("The external judge could not complete the evaluation") from exc


def _poll(base_url, token, headers, deadline=None):
    poll_deadline = time.monotonic() + float(os.getenv("JUDGE0_TIMEOUT_SECONDS", "15"))
    if deadline is not None:
        poll_deadline = min(poll_deadline, deadline)
    while time.monotonic() < poll_deadline:
        request = Request(f"{base_url}/submissions/{quote(token, safe='')}?base64_encoded=false", headers=headers)
        try:
            with urlopen(request, timeout=min(3, max(0.1, poll_deadline - time.monotonic()))) as response:
                result = json.loads(response.read(MAX_OUTPUT_BYTES + 1))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise EvaluationError("The external judge could not complete the evaluation") from exc
        if not isinstance(result, dict) or not isinstance(result.get("status"), dict):
            raise EvaluationError("The judge returned a malformed polling response")
        if result["status"].get("id") not in (1, 2):
            return result
        time.sleep(0.3)
    raise EvaluationError("The judge did not return a result before the evaluation timeout")


def _safe_text(value):
    return str(value or "The judge did not provide error details.")[:4000]
