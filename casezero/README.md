# CaseZero — AI Dispute Resolution OS

CaseZero is a governed banking-dispute operating system for a Malaysian regional
bank. Six AI agents understand the complaint and assemble a
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
- **Axiom by CaseZero:** a governed operating agent that turns natural-language
  requests into an inspectable action docket. Reads execute safely; writes require
  role checks, explicit confirmation and a hash-addressed receipt.
- Stakeholder Control Register for bank identity, complaint contact, timezone,
  warning horizon, default workspace, Axiom availability and the automatic
  resolution kill switch. Every change is chained.
- Supabase Auth/RLS for OPS, INVESTIGATOR, COMPLIANCE and ADMIN.
- Admin-only work-email invitations with single-use password setup.
- A rate-limited public live runner: one allow-listed synthetic RFC822 complaint
  executes through the deployed model, MCP bank tools, Supabase records, signed
  posting gate, balanced journal and hash chain. Arbitrary public uploads are refused.
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
 Supabase RLS + encrypted PII + append-only hash chains + balanced journal
                                                          │
 Next.js operations PWA ← authenticated API + incremental SSE ← Axiom docket
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

Open `http://localhost:3000`. A new visitor first sees one clear action: **Run a
Live Complaint**. The input is an allow-listed fictional customer, while the API,
model, tool calls, Supabase writes, journal and audit proof are live. The existing
mutation-free operating rehearsal remains a secondary option. Staff select
**Staff sign in**. The four synthetic identities are
`ops@casezero.my`, `investigator@casezero.my`, `compliance@casezero.my` and
`admin@casezero.my`; they use the password supplied to the seeder. Offline
Rehearsal works without an authenticated session and never mutates bank data.

Admins add real colleagues under **Operators** by entering a full name, work email
and least-privilege role. Supabase sends a single-use invitation to `/set-password`;
after password setup, the `app_users` role row controls Postgres RLS. There is no
public staff registration endpoint.

## First day for a stakeholder

1. Open **Run a Live Complaint** and inspect the fresh case reference, actual model
   and MCP receipts, PASS gate, balanced journal and verified chain.
2. Use **Explore the Operations Workspace** only after the live case is clear; its
   records and mutations remain an explicitly labelled rehearsal.
3. Sign in as an Admin and open **Settings** to set the bank name, complaint inbox,
   Malaysian timezone, SLA warning horizon and automation posture.
4. Open **Operators**, enter each colleague's work email and assign the least
   privileged role. The invitation is single use; there is no open registration.
5. Use **Axiom** from any staff page. It shows the action, authority, effect and
   gates before execution. Settings and invitations always require confirmation.
6. Keep automatic resolution off during shadow mode, validate the evaluation and
   journal evidence, then enable it only after Compliance approves the rule packs.

The stakeholder release is live at <https://casezero-alpha.vercel.app>. It is ready
today for onboarding, rehearsal and a synthetic-data pilot. Connecting real customer
mail and financial posting requires the bank-controlled credentials listed in
`DEPLOYMENT.md`; the repository never contains them.

The final production recheck created `MYB-2026-000031` and returned `COMMUNICATED`,
`PASS`, `POSTED`, a balanced RM2,450 journal, three metered Gemini calls, three MCP
bank-tool calls and a valid 13-link chain in 26.54 seconds. Its persisted public
proof is <https://casezero-alpha.vercel.app/live?run=CA1NdXDduzdYnVZXvzeBSHjTIQD4uIrcWz18oFvrMQI>.

New operators can follow [STAKEHOLDER_GUIDE.md](STAKEHOLDER_GUIDE.md). The
case-study gap analysis and production boundary are recorded in
[STAKEHOLDER_READINESS_REVIEW.md](STAKEHOLDER_READINESS_REVIEW.md), and every
hackathon upload artifact is organised under [submission/](submission/README.md).

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
npm audit --audit-level=high
```

The current release gate is **466 Python tests**, **14 Playwright stakeholder
journeys**, a clean production build/typecheck and **0 npm vulnerabilities**.

Record the chaptered stakeholder walkthrough at 1920×1080, then build the narrated
H.264 film and WebVTT transcript from the exact captured timeline:

```bash
cd dashboard
DEMO_BASE_URL=https://casezero-alpha.vercel.app npm run demo:record
npm run demo:build
```

The verified submission film is `submission/04-demo/CaseZero-Stakeholder-Demo.mp4`
(5:55.77, 1080p, narrated) with `CaseZero-Stakeholder-Demo.en.vtt` captions. Its
explanatory frames come from the final Axiom deck; the archived decorative deck is
not used in the film or submission.

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
- [`SUBMISSION.md`](SUBMISSION.md) — case-study fit and external evidence list.
- [`MOTION_AUDIT.md`](MOTION_AUDIT.md) and
  [`WEB_INTERFACE_AUDIT.md`](WEB_INTERFACE_AUDIT.md) — release audits.
