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

## Production web deployment on Vercel

The root `vercel.json` uses Vercel Services to publish the Next.js dashboard at `/`
and rewrite `/api/*` to FastAPI from one project, so browser requests stay on the
same HTTPS origin. Python dependencies are declared in the root `pyproject.toml`;
`api/pyproject.toml` also supports deploying the API directory independently.

```bash
vercel link
vercel env add SUPABASE_URL production
# add the remaining required values from .env.example through the encrypted prompt
npx --yes vercel@58.4.4 deploy --prod --yes
```

The Services deployment endpoint currently refuses the older 41.x CLI bundled on
this host. Keep the release command pinned at 58.4.4 (or a separately reviewed newer
version) instead of depending on an unpinned global install.

After the first production URL exists, set `DASHBOARD_BASE_URL` to that exact HTTPS
origin and redeploy. Add both `https://<production-host>/set-password` and the site
origin to Supabase Auth's allowed redirect URLs/site URL. Keep `MCP_TRANSPORT=inproc`
on Vercel; stdio MCP remains the preferred container deployment. The SLA supervisor
is a separate long-running process and must not be started inside a serverless API.

New stakeholders only need the production URL. `/` sends them to `/live`, where an
allow-listed synthetic complaint runs through the real deployed API and produces a
persisted proof. Public callers cannot submit their own email or PII. The older
read-only operations rehearsal remains secondary. Staff accounts are
invitation-only: an Admin uses
**Operators**, Supabase emails the recipient, and the recipient creates a password at
`/set-password`.

Current production origin: <https://casezero-alpha.vercel.app>.

The Vercel deployment serves the interactive web/API boundary. The always-on SLA
supervisor remains a separately deployed single worker; do not treat a serverless
request as a scheduler. Until that worker is installed in the bank environment,
`python -m api.jobs --once` is the controlled operational smoke.

## Environment

Set all production values from `.env.example` in the host's secret manager. The
dashboard's three `NEXT_PUBLIC_*` values are public build-time configuration, not
secrets. Set `DASHBOARD_BASE_URL` to the final HTTPS origin so CORS is exact.

Required for the live web path:

- `GOOGLE_API_KEY` or another configured model key
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `FERNET_KEY`, `WORKBUDDY_INTAKE_TOKEN`
- `API_BASE_URL`, `DASHBOARD_BASE_URL`
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (dashboard build)
- `PUBLIC_LIVE_DEMO_ENABLED`, `PUBLIC_LIVE_DEMO_DAILY_LIMIT`,
  `PUBLIC_LIVE_DEMO_HOURLY_LIMIT` (non-secret deployment controls)

Optional channel credentials: Gmail IMAP/app password, Telegram bot token and VAPID
keys. The presenter-mode proactive alert does not depend on browser push permission.

## Release order

1. Apply all SQL migrations in numeric order with `python -m api.db.bootstrap`.
   Production must include `005_stakeholder_controls.sql`,
   `006_stakeholder_privilege_hardening.sql` and the Supabase CLI migration
   `20260804060651_public_live_demo.sql`. The latter owns atomic case references,
   RLS-protected run proofs and server-only rate-limit reservation.
2. Run `python -m api.db.seed`; it is idempotent and contains synthetic data only.
3. Set a temporary `DEMO_USER_PASSWORD` and run `python -m api.db.seed_users`.
4. Build and release the API; require `/health` to return `ok: true`.
5. Run `python -m api.jobs --once`, then start exactly one scheduler worker.
6. Build the dashboard with the final public API/Supabase values and release it.
7. Sign in once as every role; confirm the investigator's RLS-filtered register.
8. Run all 14 Playwright journeys, then execute `/demo/live` once and prove a fresh
   `COMMUNICATED` case, actual telemetry/tool receipts, balanced journal and valid chain.
9. Remove `DEMO_USER_PASSWORD` from the long-lived runtime after identities exist.

## Stakeholder control and inbox onboarding

- The first Admin opens **Settings** and records the real bank name, complaint inbox,
  timezone, warning horizon, default workspace and automation posture. The API
  writes an append-only settings event with a chained hash.
- The Admin opens **Operators** to invite colleagues by work email and assign OPS,
  INVESTIGATOR, COMPLIANCE or ADMIN. Supabase sends the single-use password link.
- The email value in Settings is the customer-facing contact used by letters and
  referral material. Receiving mail still requires the bank's IMAP/forwarding
  secret or a bank-owned webhook; a text field is not mailbox access.
- Leave automatic resolution off until core banking/CRM MCP endpoints, signed ticket
  custody, rule packs and outbound templates have bank approval.
- Axiom may summarise and navigate immediately. Its write capabilities remain
  allowlisted, role checked, explicitly confirmed and receipt logged.

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
- 466-test Python suite, typecheck, production build, 14 Playwright journeys, MCP,
  LLM, database and mailbox-channel smokes pass.
