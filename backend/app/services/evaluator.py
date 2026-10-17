"""Judge0-backed evaluation. Submitted code is only sent to the configured sandbox."""
import json
import os
import time
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


LANGUAGES = {"python": 71, "java": 62}
MAX_CODE_BYTES = 50_000
MAX_INPUT_BYTES = 10_000
MAX_OUTPUT_BYTES = 50_000
MAX_TEST_CASES = 50
USER_AGENT = "CodeX/1.0"

# Judge0 status ids: https://ce.judge0.com/#statuses-and-languages-status-get
STATUS_PENDING = (1, 2)
STATUS_ACCEPTED = 3
STATUS_WRONG_ANSWER = 4
STATUS_TIME_LIMIT = 5
STATUS_COMPILATION_ERROR = 6
STATUS_RUNTIME_ERRORS = (7, 8, 9, 10, 11, 12, 14)
STATUS_INTERNAL_ERROR = 13


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
    """Evaluation cannot run because of configuration (no judge, no usable test cases)."""


class EvaluationError(Exception):
    """The judge was contacted but did not produce a trustworthy verdict."""


def validate_test_cases(raw_cases):
    """Return well-formed test cases or raise EvaluationUnavailable.

    A case must be a mapping with string ``input`` and ``expected_output``
    values. Misconfigured cases must never turn into a verdict.
    """
    if not raw_cases:
        raise EvaluationUnavailable("Evaluation is unavailable: this problem has no configured test cases")
    if not isinstance(raw_cases, list):
        raise EvaluationUnavailable("Evaluation is unavailable: this problem's test cases are misconfigured")
    if len(raw_cases) > MAX_TEST_CASES:
        raise EvaluationUnavailable("Evaluation is unavailable: this problem exceeds the configured test case limit")
    cases = []
    for case in raw_cases:
        if not isinstance(case, dict):
            raise EvaluationUnavailable("Evaluation is unavailable: this problem's test cases are misconfigured")
        input_data = case.get("input", "")
        expected = case.get("expected_output")
        if not isinstance(input_data, str) or not isinstance(expected, str):
            raise EvaluationUnavailable("Evaluation is unavailable: this problem's test cases are misconfigured")
        if len(input_data.encode("utf-8")) > MAX_INPUT_BYTES:
            raise EvaluationUnavailable("Evaluation is unavailable: a configured test input exceeds the judge limit")
        cases.append({"input": input_data, "expected_output": expected})
    return cases


def normalize_output(text) -> str:
    """Compare program output leniently: ignore trailing whitespace on each
    line, Windows line endings, and trailing blank lines."""
    lines = [line.rstrip() for line in str(text or "").replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def evaluate_submission(problem, source_code: str, language: str) -> Evaluation:
    language = language.strip().lower()
    if language not in LANGUAGES:
        raise ValueError("Supported languages are python and java")
    if len(source_code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ValueError("Source code exceeds the 50000 byte limit")
    cases = validate_test_cases(problem.test_cases)
    base_url = os.getenv("JUDGE0_URL", "").strip().rstrip("/")
    if not base_url:
        raise EvaluationUnavailable("Evaluation is unavailable: configure JUDGE0_URL")

    deadline = time.monotonic() + float(os.getenv("JUDGE0_EVALUATION_TIMEOUT_SECONDS", "35"))
    for index, case in enumerate(cases, start=1):
        if time.monotonic() >= deadline:
            raise EvaluationError("The evaluation exceeded its overall time limit")
        result = _judge(source_code, language, case["input"], base_url, deadline=deadline)
        status_data = result.get("status") if isinstance(result, dict) else None
        status = status_data.get("id") if isinstance(status_data, dict) else None
        if status in (STATUS_ACCEPTED, STATUS_WRONG_ANSWER):
            actual = normalize_output(result.get("stdout"))
            if status == STATUS_WRONG_ANSWER or actual != normalize_output(case["expected_output"]):
                return Evaluation("Wrong Answer", False, failed_test=index,
                                  actual_output=actual[:MAX_OUTPUT_BYTES])
            continue
        if status == STATUS_TIME_LIMIT:
            return Evaluation("Time Limit Exceeded", False, error="The program exceeded the judge time limit.", failed_test=index)
        if status == STATUS_COMPILATION_ERROR:
            return Evaluation("Compilation Error", False, error=_safe_text(result.get("compile_output")), failed_test=index)
        if status in STATUS_RUNTIME_ERRORS:
            return Evaluation("Runtime Error", False, error=_safe_text(result.get("stderr") or result.get("message")), failed_test=index)
        if status == STATUS_INTERNAL_ERROR:
            raise EvaluationError("The judge reported an internal execution error")
        raise EvaluationError("The judge returned an unsupported or unsuccessful status")
    return Evaluation("Accepted", True)


def _auth_headers(base_url):
    """Judge0 CE / self-hosted instances use X-Auth-Token; RapidAPI-hosted
    instances use the RapidAPI key headers. The key is never logged.

    An explicit User-Agent is required: Cloudflare-fronted judges (including
    the public CE instance) block urllib's default "Python-urllib" agent."""
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT}
    key = os.getenv("JUDGE0_API_KEY", "").strip()
    if not key:
        return headers
    host = (urlparse(base_url).hostname or "").lower()
    header_name = os.getenv("JUDGE0_AUTH_HEADER", "").strip()
    if header_name:
        headers[header_name] = key
    elif host.endswith(".rapidapi.com"):
        headers["X-RapidAPI-Key"] = key
        headers["X-RapidAPI-Host"] = host
    else:
        headers["X-Auth-Token"] = key
    return headers


def _judge(code, language, input_data, base_url, deadline=None):
    payload = {"source_code": code, "language_id": LANGUAGES[language], "stdin": input_data}
    url = f"{base_url}/submissions?base64_encoded=false&wait=false"
    headers = _auth_headers(base_url)
    request = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        timeout = float(os.getenv("JUDGE0_TIMEOUT_SECONDS", "15"))
        if deadline is not None:
            timeout = min(timeout, max(0.1, deadline - time.monotonic()))
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read(MAX_OUTPUT_BYTES + 1))
        if not isinstance(result, dict):
            raise EvaluationError("The judge returned a malformed response")
        status_data = result.get("status")
        status = status_data.get("id") if isinstance(status_data, dict) else None
        if result.get("token") and (status is None or status in STATUS_PENDING):
            return _poll(base_url, result["token"], headers, deadline=deadline)
        return result
    except HTTPError as exc:
        raise EvaluationError(_http_error_message(exc)) from exc
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise EvaluationError("The external judge could not complete the evaluation") from exc


def _poll(base_url, token, headers, deadline=None):
    poll_deadline = time.monotonic() + float(os.getenv("JUDGE0_TIMEOUT_SECONDS", "15"))
    if deadline is not None:
        poll_deadline = min(poll_deadline, deadline)
    while time.monotonic() < poll_deadline:
        request = Request(f"{base_url}/submissions/{quote(str(token), safe='')}?base64_encoded=false", headers=headers)
        try:
            with urlopen(request, timeout=min(3, max(0.1, poll_deadline - time.monotonic()))) as response:
                result = json.loads(response.read(MAX_OUTPUT_BYTES + 1))
        except HTTPError as exc:
            raise EvaluationError(_http_error_message(exc)) from exc
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise EvaluationError("The external judge could not complete the evaluation") from exc
        if not isinstance(result, dict) or not isinstance(result.get("status"), dict):
            raise EvaluationError("The judge returned a malformed polling response")
        if result["status"].get("id") not in STATUS_PENDING:
            return result
        time.sleep(0.3)
    raise EvaluationError("The judge did not return a result before the evaluation timeout")


def _http_error_message(exc: HTTPError) -> str:
    if exc.code == 401:
        return "The external judge rejected the configured credentials"
    if exc.code == 403:
        # A 403 can come from the judge (bad key or header type) or from a CDN
        # in front of it blocking the request, so do not assume credentials.
        return ("The external judge refused the request (HTTP 403); check JUDGE0_API_KEY "
                "and JUDGE0_AUTH_HEADER, or whether a proxy/CDN in front of the judge is blocking it")
    if exc.code == 429:
        return "The external judge is rate limiting requests; try again shortly"
    return f"The external judge returned HTTP {exc.code}"


def _safe_text(value):
    return str(value or "The judge did not provide error details.")[:4000]
