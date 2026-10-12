# PatternIQ (CodeX)

PatternIQ is a coding-practice and pattern-mastery app. Learners submit Python
or Java solutions; the backend runs them in an external **Judge0** sandbox,
stores the verdict, updates per-pattern mastery, records mistakes with
feedback, and recommends the next problem. Code is never executed inside the
FastAPI process, and the browser never decides a verdict.

- Backend: FastAPI + SQLAlchemy (`backend/`)
- Frontend: Next.js 16 (`frontend/`)
- Database: PostgreSQL (via `docker-compose.yml`) or an isolated SQLite demo file
- Seed data: `data/patterns.json`, `data/problems.json`, `data/test_cases.json`

37 of the 50 seeded problems have verified console input/output test cases and
can be evaluated. The remaining 13 (tree, graph, and class-design problems) are
catalog entries only; the UI marks them "not evaluable" and recommendations
skip them.

## Quick start with an isolated demo database (PowerShell)

These steps never read or write the PostgreSQL database. The seed command
refuses to run against anything other than SQLite unless you pass `--confirm`.

### 1. Backend

```powershell
cd backend
if (!(Test-Path .\venv\Scripts\python.exe)) { python -m venv venv }
.\venv\Scripts\python.exe -m pip install -r requirements.txt

# Pick a NEW file name if codex-demo.sqlite3 already exists and you want a clean slate.
$env:DATABASE_URL = "sqlite:///./codex-demo.sqlite3"
$env:JUDGE0_URL = ""          # leave blank until you have a judge (see below)
.\venv\Scripts\python.exe -m app.seed
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The API is now at `http://127.0.0.1:8000` (interactive docs at `/docs`).
Environment variables set in the shell take precedence over `backend/.env`,
so the commands above are safe even if `.env` points at PostgreSQL.

### 2. Frontend (second terminal)

```powershell
cd frontend
if (!(Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm ci
npm run dev
```

Open `http://localhost:3000` and click **Start practicing**. The Next.js
rewrite forwards `/api/backend/*` to `BACKEND_API_URL` (default
`http://127.0.0.1:8000`); nothing in the frontend bundle contains secrets.

### 3. Create a learner and submit

On the practice page, use **Need a learner ID?** to create a learner; the ID
is filled in and remembered in the browser. Or use the API:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/users/ -ContentType "application/json" -Body '{"name":"Learner","email":"learner@example.com"}'
Invoke-RestMethod http://127.0.0.1:8000/problems/ | Select-Object id, title, test_cases_available
```

Each evaluable problem's description states its stdin/stdout contract and the
page shows the visible sample cases. A Python solution for **Binary Search**
(`external_id` 704):

```python
import sys
data = sys.stdin.read().split()
n = int(data[0]); nums = list(map(int, data[1:1 + n])); target = int(data[1 + n])
lo, hi = 0, n - 1
while lo <= hi:
    mid = (lo + hi) // 2
    if nums[mid] == target:
        print(mid); break
    if nums[mid] < target: lo = mid + 1
    else: hi = mid - 1
else:
    print(-1)
```

Java submissions must define `public class Main` with a `main` method and read
from `System.in`.

On a freshly seeded database Binary Search has `id` 11; confirm with
`GET /problems/` before submitting.

```powershell
$body = @{ user_id = 1; problem_id = 11; language = "python"; code = "print(-1)" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/submissions/ -ContentType "application/json" -Body $body
```

The response contains the server verdict (`status`, `is_correct`),
`evaluation_details` (failed test number, judge diagnostics, your output,
feedback), the updated `mastery`, a `mistake` for incorrect results, and a
`recommendation`. Any `status` / `is_correct` fields sent by the client are
ignored.

## Judge0 configuration

Without a judge the API returns HTTP 503 for every submission and saves
nothing. To enable evaluation, set in `backend/.env` (or the shell):

| Variable | Meaning |
| --- | --- |
| `JUDGE0_URL` | Base URL of a Judge0 CE instance, e.g. `https://ce.judge0.com` or your own |
| `JUDGE0_API_KEY` | Optional. Sent as `X-Auth-Token`; for `*.rapidapi.com` hosts it is sent as `X-RapidAPI-Key` automatically |
| `JUDGE0_AUTH_HEADER` | Optional override for the header name |
| `JUDGE0_TIMEOUT_SECONDS` | Per-request timeout (default 15) |
| `JUDGE0_EVALUATION_TIMEOUT_SECONDS` | Budget for all test cases of one submission (default 35; keep below the frontend's 45 s request timeout) |

Submissions are created with `wait=false` and polled by token. Language IDs:
Python `71`, Java `62`. Source is limited to 50,000 bytes, inputs to 10,000
bytes, and 50 test cases per problem. Output comparison ignores trailing
whitespace and Windows line endings.

Test cases live in `data/test_cases.json`, keyed by the problem's
`external_id`, each shaped `{"input": "...", "expected_output": "...", "visible": true|false}`.
Only `visible` cases are sent to the browser. Every expected output is checked
by `backend/tests/test_seed_data.py` against the reference solutions in
`backend/tests/reference_solutions.py`.

## Optional AI feedback

Set `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL` in `backend/.env` for an
OpenAI-compatible `/chat/completions` service. Feedback is advisory only: it
never changes a verdict, and if the provider is missing or fails, the saved
feedback is rule-based and labelled `provider: rule_based`.

## Using PostgreSQL instead

```powershell
docker compose up -d        # postgres on host port 5433
cd backend
Copy-Item .env.example .env # then edit DATABASE_URL etc.
.\venv\Scripts\python.exe -m app.seed --confirm
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Startup runs `create_all` and adds the `problems.test_cases` and
`submissions.evaluation_details` JSON columns to older databases. There is no
migration framework. Seeding is idempotent: existing patterns and problems are
untouched, and test cases are only added to problems that have none.

## Verification

```powershell
cd backend
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

```powershell
cd frontend
npm run lint
npm run build
```

| Check | Uses live services? |
| --- | --- |
| Backend unit tests (59) | No. Judge0 and the AI provider are mocked; databases are in-memory SQLite |
| Frontend lint / build | No |
| `backend/scripts/live_judge0_check.py` | **Yes.** Contacts the configured judge through the running API. See `docs/live-judge0-test-plan.md`; run only when you approve live testing |

## Interpreting common errors

| Response | Meaning |
| --- | --- |
| `503 Evaluation is unavailable: configure JUDGE0_URL` | No judge configured; nothing was saved |
| `503 ... this problem has no configured test cases` / `... misconfigured` | Problem cannot be evaluated; nothing was saved |
| `502 Evaluation Error: ... rejected the configured credentials` | Judge returned 401/403; check the key and header type |
| `502 Evaluation Error: ... rate limiting` | Judge returned 429 |
| `502 Evaluation Error: ... did not return a result before the evaluation timeout` | Judge queue too slow for the configured budget |
| `422 Supported languages are python and java` | Unsupported language |
| `404 User not found` / `Problem not found` | Bad IDs |
| Frontend: "The request timed out before the judge finished" | 45 s client timeout; the backend may still have saved the attempt, so wait before retrying |

## Security notes

There is no authentication layer. `user_id` is supplied by the client and
trusted, and the list endpoints (`/submissions/`, `/mastery/`, `/mistakes/`)
accept an optional `user_id` filter but are not access-controlled. This is
acceptable for a local demo only; put the API behind authentication before
exposing it. Keep all keys in `backend/.env`, which is git-ignored.

## Project layout

```
backend/app/routes        FastAPI routers (users, patterns, problems, submissions, mistakes, mastery, recommendations)
backend/app/services      evaluator (Judge0), feedback, mastery, mistake, recommendation
backend/app/seed.py       idempotent seeding with the SQLite-only safety guard
backend/tests             unittest suite (mocked judge/AI) + reference solutions
backend/scripts           live_judge0_check.py (manual, live)
data/                     patterns, problems, verified test cases
frontend/app/practice     practice page and API client
docs/                     live Judge0 test plan
```
