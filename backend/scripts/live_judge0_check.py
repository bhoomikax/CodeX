r"""Live Judge0 verification against a RUNNING backend and an ISOLATED demo database.

This script is deliberately not part of the automated test suite: it contacts
the real judge configured in backend/.env through the backend API. Run it only
after approving live testing. It never prints secret values.

Usage (PowerShell, from the backend directory, with the API running on :8000):

    .\venv\Scripts\python.exe scripts\live_judge0_check.py --api http://127.0.0.1:8000

Steps performed:
  1. Report judge configuration (URL host + whether a key is set; no values).
  2. Create a throwaway learner.
  3. Submit a correct Python solution to Binary Search (external_id 704).
  4. Submit a correct Java solution.
  5. Submit a wrong answer.
  6. Submit code with a compilation error (Java) and a runtime error (Python).
  7. Confirm the saved verdicts, evaluation details, mastery counters and mistakes.
  8. Print a summary. Unavailable-judge behaviour (HTTP 503 without saved rows)
     is covered by the unit tests; to check it live, blank JUDGE0_URL and resubmit.
"""
import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PYTHON_CORRECT = """import sys
data = sys.stdin.read().split()
n = int(data[0]); nums = list(map(int, data[1:1 + n])); target = int(data[1 + n])
lo, hi = 0, n - 1
ans = -1
while lo <= hi:
    mid = (lo + hi) // 2
    if nums[mid] == target:
        ans = mid; break
    if nums[mid] < target:
        lo = mid + 1
    else:
        hi = mid - 1
print(ans)
"""

JAVA_CORRECT = """import java.util.*;
public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        int[] nums = new int[n];
        for (int i = 0; i < n; i++) nums[i] = sc.nextInt();
        int target = sc.nextInt();
        int lo = 0, hi = n - 1, ans = -1;
        while (lo <= hi) {
            int mid = (lo + hi) / 2;
            if (nums[mid] == target) { ans = mid; break; }
            if (nums[mid] < target) lo = mid + 1; else hi = mid - 1;
        }
        System.out.println(ans);
    }
}
"""

PYTHON_WRONG = "print(0)\n"
JAVA_COMPILE_ERROR = "public class Main { public static void main(String[] a) { int x = ; } }\n"
PYTHON_RUNTIME_ERROR = "import sys\nprint(1 / 0)\n"


def call(api, method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(f"{api}{path}", data=data, method=method,
                      headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read())
        except Exception:
            payload = None
        return exc.code, payload


def report_configuration():
    url = os.getenv("JUDGE0_URL", "")
    host = urlparse(url).hostname if url else None
    print(f"[1] JUDGE0_URL host: {host or '(not set)'}; API key configured: {bool(os.getenv('JUDGE0_API_KEY'))}")
    print(f"    AI feedback configured: {bool(os.getenv('AI_API_KEY'))}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    api = args.api.rstrip("/")

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    report_configuration()

    status, problems = call(api, "GET", "/problems/")
    if status != 200:
        print(f"Backend not reachable or /problems/ failed: HTTP {status}")
        return 1
    demo = next((p for p in problems if p.get("external_id") == "704" and p.get("test_cases_available")), None)
    if not demo:
        print("Binary Search (704) with test cases not found. Seed the demo database first.")
        return 1
    print(f"    Using problem #{demo['id']} {demo['title']}")

    status, user = call(api, "POST", "/users/", {"name": "Live Check", "email": f"live-{int(time.time())}@example.com"})
    if status != 200:
        print(f"[2] Could not create learner: HTTP {status} {user}")
        return 1
    print(f"[2] Created learner #{user['id']}")

    checks = [
        ("[3] Python correct", "python", PYTHON_CORRECT, "Accepted"),
        ("[4] Java correct", "java", JAVA_CORRECT, "Accepted"),
        ("[5] Wrong answer", "python", PYTHON_WRONG, "Wrong Answer"),
        ("[6a] Java compilation error", "java", JAVA_COMPILE_ERROR, "Compilation Error"),
        ("[6b] Python runtime error", "python", PYTHON_RUNTIME_ERROR, "Runtime Error"),
    ]
    failures = 0
    for label, language, code, expected in checks:
        status, body = call(api, "POST", "/submissions/", {
            "user_id": user["id"], "problem_id": demo["id"], "language": language, "code": code,
        })
        if status != 200:
            failures += 1
            print(f"{label}: HTTP {status} {body and body.get('detail')}")
            continue
        ok = body["status"] == expected
        failures += 0 if ok else 1
        details = body.get("evaluation_details") or {}
        print(f"{label}: got {body['status']!r} (expected {expected!r}) {'OK' if ok else 'MISMATCH'}; "
              f"failed_test={details.get('failed_test')} mastery={body['mastery']['correct_attempts']}/"
              f"{body['mastery']['total_attempts']} streak={body['mastery']['consecutive_correct']} "
              f"mistake={'yes' if body.get('mistake') else 'no'} feedback={details.get('feedback', {}).get('provider')}")

    status, saved = call(api, "GET", f"/submissions/?user_id={user['id']}")
    status_m, mastery = call(api, "GET", f"/mastery/?user_id={user['id']}")
    status_k, mistakes = call(api, "GET", f"/mistakes/?user_id={user['id']}")
    print(f"[7] Saved submissions: {len(saved) if status == 200 else status}; "
          f"mastery rows: {len(mastery) if status_m == 200 else status_m}; "
          f"mistakes: {len(mistakes) if status_k == 200 else status_k}")
    expected_mistakes = sum(1 for _, _, _, verdict in checks if verdict != "Accepted")
    if status == 200 and len(saved) != len(checks):
        failures += 1
        print("    MISMATCH: submission count")
    if status_k == 200 and len(mistakes) != expected_mistakes:
        failures += 1
        print("    MISMATCH: mistake count")
    print(f"[8] Result: {'ALL CHECKS PASSED' if failures == 0 else f'{failures} CHECK(S) FAILED'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
