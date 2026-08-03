# CaseZero Deployment Runbook

## Services

Deploy three processes from the same API image and one dashboard image:

| Process | Command | Scale |
|---|---|---:|
| API | `uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1` | 1+ |
| SLA supervisor | `python -m api.jobs` | exactly 1 |
| Dashboard | `node server.js` from the standalone Next build | 1+ |

The API is stateless except for MCP subprocess sessions. Supabase is the system of
record. Do not start the supervisor inside FastAPI; each web replica would otherwise
own a scheduler.

## Judge deployment on Vercel

The root `vercel.json` uses Vercel Services to publish the Next.js dashboard at `/`
and FastAPI at `/api` from one project. The service key `api` supplies
`NEXT_PUBLIC_API_URL=/api` automatically, so browser requests stay on the same
HTTPS origin. Python dependencies are declared in `api/pyproject.toml`.

```bash
vercel link
vercel env add SUPABASE_URL production
# add the remaining required values from .env.example through the encrypted prompt
vercel deploy --prod
```

After the first production URL exists, set `DASHBOARD_BASE_URL` to that exact HTTPS
origin and redeploy. Add both `https://<production-host>/set-password` and the site
origin to Supabase Auth's allowed redirect URLs/site URL. Keep `MCP_TRANSPORT=inproc`
on Vercel; stdio MCP remains the preferred container deployment. The SLA supervisor
is a separate long-running process and must not be started inside a serverless API.

Judges only need the production URL. `/` explains the product and starts a labelled,
read-only rehearsal without login. Staff accounts are invitation-only: an Admin uses
**Operators**, Supabase emails the recipient, and the recipient creates a password at
`/set-password`.

## Environment

Set all production values from `.env.example` in the host's secret manager. The
dashboard's three `NEXT_PUBLIC_*` values are public build-time configuration, not
secrets. Set `DASHBOARD_BASE_URL` to the final HTTPS origin so CORS is exact.

Required for the judged live path:

- `GOOGLE_API_KEY` or another configured model key
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `FERNET_KEY`, `WORKBUDDY_INTAKE_TOKEN`
- `API_BASE_URL`, `DASHBOARD_BASE_URL`
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (dashboard build)

Optional channel credentials: Gmail IMAP/app password, Telegram bot token and VAPID
keys. The presenter-mode proactive alert does not depend on browser push permission.

## Release order

1. Apply all SQL migrations in numeric order with `python -m api.db.bootstrap`.
2. Run `python -m api.db.seed`; it is idempotent and contains synthetic data only.
3. Set a temporary `DEMO_USER_PASSWORD` and run `python -m api.db.seed_users`.
4. Build and release the API; require `/health` to return `ok: true`.
5. Run `python -m api.jobs --once`, then start exactly one scheduler worker.
6. Build the dashboard with the final public API/Supabase values and release it.
7. Sign in once as every role; confirm the investigator's RLS-filtered register.
8. Run Playwright against the public URL and execute one live WorkBuddy smoke.
9. Remove `DEMO_USER_PASSWORD` from the long-lived runtime after identities exist.

## Rollback

- Dashboard/API images are immutable; roll back to the prior image digest.
- Policy changes are versioned. Apply the prior YAML as a new version; never rewrite
  the append-only policy history.
- Financial entries are never deleted. Correct them with a new balanced compensating
  journal entry under the same governed ticket path.
- If the network is unreliable, start the emergency Compose overlay and use the
  labelled Offline Rehearsal UI. It makes no bank or model calls.

## Go-live checks

- HTTPS only; Supabase redirect URL matches the dashboard origin.
- CORS contains only the dashboard origin.
- `.env` absent from image layers and source control.
- API logs expose no bearer tokens, PII, raw account numbers or encryption keys.
- Four-role auth smoke, RLS visibility smoke and exact-chain verification pass.
- `pytest`, typecheck, production build, Playwright, MCP, LLM and WorkBuddy smokes pass.
