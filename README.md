# CodeX

CodeX is a coding practice and personalized learning app. Submission correctness is determined by the configured external Judge0 service; code is never executed inside the FastAPI process. The bundled problems are mostly catalog entries without runnable input/output test cases. The seeded **Binary Search** problem (`external_id=704`) is a console-I/O demonstration with sample and hidden cases.

## Setup

1. For PostgreSQL, `docker compose up -d` maps host port `5433` to container port `5432`. The checked-in `.env.example` matches this mapping. In `backend`, copy it to `.env` and set `DATABASE_URL`. Startup creates tables and adds the two JSON columns to existing databases; no Alembic migration system exists in this project.
2. Install backend dependencies:

   ```powershell
   cd backend
   if (!(Test-Path .\venv\Scripts\python.exe)) { python -m venv venv }
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. To prepare an isolated demo database, use a **new filename** from the `backend` directory. These commands do not seed the `DATABASE_URL` stored in `.env`:

   ```powershell
   $env:DATABASE_URL = "sqlite:///./codex-demo.sqlite3"
   .\venv\Scripts\python.exe -m app.seed
   .\venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

   If `codex-demo.sqlite3` already exists, choose another new filename rather than overwriting it. The seed operation is idempotent for existing catalog rows, but adds the Binary Search demonstration cases to that database.

4. Create a user with `POST /users/` (example below) and keep the returned ID. In `frontend`, copy `.env.example` to `.env.local`, then run `npm ci` and `npm run dev`. The Next rewrite sends `/api/backend` requests to `BACKEND_API_URL`.

For live evaluation, set `JUDGE0_URL` and, if your Judge0 instance requires it, `JUDGE0_API_KEY` in `backend/.env`. Judge timeouts are limited by `JUDGE0_TIMEOUT_SECONDS` (default 15). If no judge URL is configured, submissions return HTTP 503 and do not save an unevaluated attempt or update mastery. Problems without test cases return the same response. Add cases to a problem's `test_cases` JSON list, each shaped as `{"input":"...","expected_output":"...","visible":false}`. Judge input/output is stdin/stdout; Java submissions should use Judge0's `Main` entry point.

### Optional AI feedback

Set `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL` in `backend/.env` for an OpenAI-compatible `/chat/completions` service. Without credentials (or if the provider fails), the saved feedback uses a rule-based explanation and marks `provider` as `rule_based`. AI feedback is advisory and cannot change judge correctness. Keep credentials on the backend only.

## API example

Create a user:

```http
POST /users/
Content-Type: application/json

{"name":"Learner","email":"learner@example.com"}
```

Submit code (use a seeded problem ID returned from `GET /problems/`):

```http
POST /submissions/
Content-Type: application/json

{"user_id":1,"problem_id":1,"language":"python","code":"n = int(input())\nprint(n)"}
```

The response contains the server verdict, evaluation evidence, updated mastery, optional mistake feedback, and a recommendation when one is available. Client-supplied `status` and `is_correct` fields are ignored. Supported languages are `python` and `java`; source is limited to 50,000 bytes. Never send hidden expected outputs to the frontend.

## Tests and commands

```powershell
cd backend
python -m unittest discover -s tests -v
```

```powershell
cd frontend
npm run dev
npm run lint
npm run build
```

Automated tests mock Judge0 and the optional AI provider and require no credentials. Real evaluation requires a reachable, configured sandbox judge and correctly formatted test cases for the chosen problem. The submission endpoint preserves the existing list and detail routes.
