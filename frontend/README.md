# CodeX Web Client

This Next.js 16 application provides the CodeX practice, dashboard,
recommendation, and revision pages. It sends API requests through the
same-origin `/api/backend/*` rewrite to the FastAPI service. Set
`BACKEND_API_URL` in the server environment; do not put backend or provider
credentials in browser-visible variables.

## Run locally

From the `frontend` directory, install the lockfile dependencies and start the
development server:

```powershell
npm ci
$env:BACKEND_API_URL = "http://127.0.0.1:8000"
npm.cmd run dev
```

The backend must be running with its database seeded. See the root
[CodeX README](../README.md) for the isolated SQLite setup, Judge0 settings,
and a complete submission example. If the backend uses another port, set
`BACKEND_API_URL` to that address before starting the frontend.

## Checks

```powershell
npm.cmd run lint
npm.cmd run build
```

The frontend does not contain Judge0 or AI credentials. Optional AI feedback is
configured by the backend only.
