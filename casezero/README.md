# CaseZero — AI Dispute Resolution OS

CaseZero is a governed banking-dispute automation pipeline for a synthetic
Malaysian regional bank. Six AI agents understand the complaint and assemble a
proposal; a deterministic compliance kernel controls classification confidence,
working-day SLA, verification, financial posting, dual control, customer
disclosures and the tamper-evident audit chain.

The central rule is simple: **models propose; the kernel disposes**. A model cannot
mint a posting ticket, remove the FMOS clause, write a journal entry, or bypass a
`PASS` verification result.

## What is included

- RFC822 and scanned-PDF intake with a deterministic injection firewall before any
  model call, field encryption, prompt redaction and native vision fallback.
- Seven versioned dispute-category rule packs matching the stated case-study mix.
- Real MCP protocol servers for core banking and CRM, with signed posting tickets.
- Double-entry reversals/credits, confidence routing and dual-control thresholds.
- Policy Composer: English instruction → typed intent → protected diff → 200-case
  replay → Compliance apply/reject → versioned hash chain.
- Supabase Auth/RLS for OPS, INVESTIGATOR, COMPLIANCE and ADMIN.
- Admin-only work-email invitations with single-use password setup; the public judge
  walkthrough needs no account and cannot write to bank systems.
- Next.js PWA with Simple/Pro operations views, review queue, Agent Theater SSE,
  fraud-ring radar, quarantine, audit proof, customer tracker and proactive alert.
- Four-page FMOS Referral Pack export.
- 200 labelled `.eml` files, 20 PDFs and deterministic/live evaluation runners.

## Architecture

```text
RFC822 / WorkBuddy / Proactive alert
                 │
          pre-LLM firewall
                 │
 Intake → Classifier → Verifier (MCP) → Resolver → Communicator
                 │             │             │
                 └──── deterministic compliance kernel ────┐
                                                          │
 Supabase RLS + encrypted PII + append-only hash chain + balanced journal
                                                          │
 Next.js operations PWA ← authenticated API + incremental SSE
```

## Local setup

Requirements: Python 3.11+, Node.js 22+, a Supabase project and at least one model
provider key. Python 3.13 is the verified local runtime.

```bash
cp .env.example .env
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements.txt
cd dashboard && npm ci && cp .env.local.example .env.local && cd ..
```

Fill `.env`, then apply migrations and seed the synthetic bank:

```bash
.venv/bin/python -m api.db.bootstrap
.venv/bin/python -m api.db.seed
DEMO_USER_PASSWORD='your unique 12+ character password' \
  .venv/bin/python -m api.db.seed_users
```

Copy the public Supabase URL/anon key and API URL into
`dashboard/.env.local`. Start each process in its own terminal:

```bash
.venv/bin/uvicorn api.main:app --reload --port 8000
.venv/bin/python -m api.jobs
cd dashboard && npm run dev
```

Open `http://localhost:3000`. A new visitor first sees the complete five-stop guide
and can enter the labelled judge walkthrough without an account. Staff select
**Staff sign in**. The four synthetic identities are
`ops@casezero.my`, `investigator@casezero.my`, `compliance@casezero.my` and
`admin@casezero.my`; they use the password supplied to the seeder. Offline
Rehearsal works without an authenticated session and never mutates bank data.

Admins add real colleagues under **Operators** by entering a full name, work email
and least-privilege role. Supabase sends a single-use invitation to `/set-password`;
after password setup, the `app_users` role row controls Postgres RLS. There is no
public staff registration endpoint.

## Verification

```bash
.venv/bin/python -m pytest api/tests -q
.venv/bin/python -m api.agents.smoke
.venv/bin/python -m api.mcp_tools.smoke
.venv/bin/python -m api.llm.smoke
.venv/bin/python -m api.db.verify_integrity
.venv/bin/python -m api.jobs --once

cd dashboard
npm run typecheck
npm run build
npm run test:e2e
```

Regenerate and evaluate the synthetic corpus:

```bash
.venv/bin/python -m api.corpus.generate_v1
.venv/bin/python -m evals.run --mode deterministic
.venv/bin/python -m evals.run --mode live --persist
```

## Containers

```bash
docker compose up --build
```

For the stage-safe UI, use the emergency overlay and choose Offline Rehearsal:

```bash
docker compose -f docker-compose.yml -f docker-compose.emergency.yml up --build
```

The scheduler runs as a single dedicated service so horizontally scaled API
workers cannot duplicate SLA events.

## Security boundaries

- `case_events` and `policy_events` are append-only and SHA-256 chained.
- Account and NRIC values are encrypted at rest; account displays are masked.
- User reads carry the user's Supabase JWT, so Postgres RLS—not React—filters data.
- Financial MCP posting requires a scoped HMAC ticket minted only after kernel
  approval. The server refuses forged, expired, wrong-case and wrong-amount tickets.
- Low confidence, ambiguous evidence, injection, and failed verification route to
  review/quarantine. They never route to a payout.
- All people, accounts, messages and transactions are synthetic.

## Documentation

- [`PROGRESS.md`](../PROGRESS.md) — current evidence-backed build state.
- [`MASTERPLAN.md`](../MASTERPLAN.md) — product/design source of truth.
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — production release runbook.
- [`SUBMISSION.md`](SUBMISSION.md) — judge-facing description and evidence list.
- [`MOTION_AUDIT.md`](MOTION_AUDIT.md) and
  [`WEB_INTERFACE_AUDIT.md`](WEB_INTERFACE_AUDIT.md) — release audits.
