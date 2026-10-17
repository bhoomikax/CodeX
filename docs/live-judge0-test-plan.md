# Live Judge0 test plan

**Status: NOT RUN.** Every automated test in this repository mocks Judge0 and
the optional AI provider. Nothing below has been executed against a real judge.
Run it only after you have approved contacting the external service and only
against an isolated SQLite demo database.

## Preconditions

1. `backend/.env` has `JUDGE0_URL` set (and `JUDGE0_API_KEY` if the instance
   requires one). The public `https://ce.judge0.com` instance is rate limited
   and may reject requests without a key; a self-hosted or RapidAPI instance
   is more reliable.
2. The backend is running against a demo database that you are happy to write
   to, for example:

   ```powershell
   cd backend
   $env:DATABASE_URL = "sqlite:///./live-check.sqlite3"
   .\venv\Scripts\python.exe -m app.seed
   .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
   ```

3. No PostgreSQL connection string is in `$env:DATABASE_URL` for that shell.

## Steps

The script `backend/scripts/live_judge0_check.py` performs the steps below
through the backend API. It never prints secret values; it only reports the
judge host name and whether a key is configured.

```powershell
cd backend
.\venv\Scripts\python.exe scripts\live_judge0_check.py --api http://127.0.0.1:8000
```

| Step | What it does | Expected result |
| --- | --- | --- |
| 1 | Reports `JUDGE0_URL` host and whether an API key is set | Host matches your configuration; no secret printed |
| 2 | Creates a throwaway learner via `POST /users/` | HTTP 200 with an ID |
| 3 | Submits a correct Python binary search to problem `704` | `Accepted`, `is_correct: true`, mastery 1/1 |
| 4 | Submits a correct Java `Main` class | `Accepted`, mastery 2/2, streak 2 |
| 5 | Submits `print(0)` | `Wrong Answer`, `failed_test` set, mistake `edge_case`, streak 0 |
| 6a | Submits Java with a syntax error | `Compilation Error`, judge diagnostic in `evaluation_details.error`, mistake `syntax_error` |
| 6b | Submits Python dividing by zero | `Runtime Error`, traceback in `evaluation_details.error`, mistake `logic_error` |
| 7 | Reads `/submissions/?user_id=`, `/mastery/?user_id=`, `/mistakes/?user_id=` | 5 submissions, 1 mastery row (2 correct of 5), 3 mistakes |
| 8 | Prints a pass/fail summary | `ALL CHECKS PASSED` |

### Unavailable-service behaviour

With the backend stopped, blank `JUDGE0_URL` in `backend/.env`, restart, and
submit again from the practice page. Expected: HTTP 503 with
`Evaluation is unavailable: configure JUDGE0_URL`, no new submission, no
mastery change. With an unreachable `JUDGE0_URL` (for example
`https://judge.invalid`), expected: HTTP 502 `Evaluation Error: ...`, and
again no rows are written.

## Interpreting failures

| Symptom | Likely cause |
| --- | --- |
| `The external judge rejected the configured credentials` | HTTP 401: wrong or missing `JUDGE0_API_KEY`, or wrong header type (set `JUDGE0_AUTH_HEADER` or use a `*.rapidapi.com` host) |
| `The external judge refused the request (HTTP 403)` | Same causes as above, or a CDN in front of the judge blocked the request (the evaluator sends `User-Agent: CodeX/1.0` because Cloudflare blocks urllib's default agent) |
| `The external judge is rate limiting requests` | Public instance quota; wait or use your own instance |
| `The judge did not return a result before the evaluation timeout` | Judge queue is slow; raise `JUDGE0_TIMEOUT_SECONDS` / `JUDGE0_EVALUATION_TIMEOUT_SECONDS` but keep the total under the frontend's 45 s |
| Java reported as `Compilation Error` on a correct solution | The class must be named `Main` |
| `Wrong Answer` with matching-looking output | Check the sample's exact format; only trailing whitespace is ignored |
