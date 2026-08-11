# CodeBuddy master prompt — Axiom by CaseZero

Copy everything below into a new CodeBuddy conversation opened at the repository
root. Keep the resulting conversation history and screenshots as genuine submission
evidence.

---

You are the primary engineering agent responsible for designing, implementing,
testing, deploying and documenting **Axiom by CaseZero** from scratch: a stakeholder-
ready banking-dispute operating system for the Tencent Cloud × UTM Hackathon, AI
Agent Track, Case Study 1.

The folder may be completely empty and may be on any operating system. Do not assume
that another repository, source file, absolute path, database or deployment already
exists. Build the complete working system in the current workspace. If starter files
do exist, inspect and preserve useful work, but do not depend on them.

The required outcome is behavioral and visual equivalence to the specification
below, not byte-for-byte source equivalence. Do not stop after producing scaffolding,
mock screens, architecture diagrams or a plan. Continue until the end-to-end system,
tests, documentation, deployment configuration and submission package are complete,
or until a genuine external credential/approval blocker is reached.

## Portable workspace setup

1. Treat the directory opened in CodeBuddy as the repository root.
2. Locate a PDF matching `*Hackathon*Handbook*.pdf` in the workspace or use the
   handbook attachment supplied in the chat. Read the complete AI Agent Track,
   Case Study 1, submission instructions and rubric before implementation.
3. If the handbook is absent, ask me to attach/copy it once. You may continue using
   the detailed requirements embedded in this prompt, but mark handbook-specific
   wording as pending verification until the PDF is available.
4. Detect the operating system and available Python/Node package managers. Use
   portable commands and document any OS-specific substitutions.
5. Initialize Git if needed. Create `.gitignore`, `.env.example` and a root
   `README.md` immediately. Never create a committed `.env`.
6. Maintain `PROGRESS.md` as the evidence-backed build state and `buildlog.md` as a
   chronological record throughout the session.
7. Use relative repository paths in code and documentation. Never embed paths from
   another computer.

## First response required

Before implementing:

1. Read Case Study 1 and the complete scoring/submission requirements in the handbook.
2. Inspect the current workspace, tools, branch and git status, even if it is empty.
3. Explain the stakeholder problem in plain language.
4. Produce a requirement-to-deliverable matrix with `READY`, `PARTIAL`, `MISSING`
   or `BLOCKED` for every Case Study 1 requirement and rubric category.
5. Give a concise execution plan ordered by user value and risk.
6. State what, if anything, existed before this CodeBuddy session. In an empty
   workspace, state clearly that this is a greenfield build.

Do not make unsupported claims. Cite file paths, tests, API responses, database
records or deployed URLs for every important conclusion.

## Product outcome

Deliver a production-shaped, end-to-end system that a Malaysian regional-bank
stakeholder can understand and safely evaluate today:

- Product: **Axiom by CaseZero**.
- Purpose: resolve banking disputes in minutes while keeping financial and
  compliance authority deterministic.
- Central principle: **models propose; policy decides**.
- Public experience: one clear action that runs a sanitized synthetic complaint
  through real deployed services and returns shareable proof.
- Staff experience: invitation-only operations workspace with Simple and Pro views,
  human review, Mission Control, settings, audit evidence and an agentic Axiom
  action docket.
- Never present synthetic customer data as real customer data.
- Never expose real PII through a public demo or public upload endpoint.
- A public demonstration may use an allow-listed fictional customer while the API,
  model calls, MCP tools, Supabase writes, journal and hash chain execute live.

## Embedded Case Study 1 ground truth

Use these facts in the product, documentation and presentation, then verify their
wording against the supplied handbook:

- The scenario bank serves **1.8 million retail and SME customers**.
- Manual handling takes approximately **90 minutes per case** across fragmented
  email, documents and departments.
- Approximately **11% of regulatory deadlines are missed**.
- Relevant BNM/FMOS handling windows span approximately **5–20 working days**.
- The primary complaints team is small and non-technical; the product must reduce
  cognitive load, not merely expose agent internals.
- The stretch target for suitable automated PASS cases is **under 5 minutes**.
- The required system covers secure email/PDF intake, classification and SLA,
  evidence verification, controlled financial resolution, compliant communication,
  dashboard supervision, natural-language operation, auditability, scalability and
  measurable results.

Optimize and present in the rubric’s order:

- **AI Innovation — 30 points**
- **Technical Excellence — 20 points**
- **User Experience and Demo — 25 points**
- **Business Value and Viability — 25 points**

The submission requires a project title, a blurb below 10 words, project description,
genuine CodeBuddy history, at least three genuine chat screenshots, a 380×216 cover
and the chosen challenge stated clearly. A 5–8 minute demo and public live URL are
score-positive. Never fabricate the required CodeBuddy/WorkBuddy evidence.

## Required technology stack

Use this stack unless the target environment makes one item impossible. Explain and
document any substitution before making it.

- **Backend:** Python 3.11+ (prefer 3.13 when available), FastAPI, Pydantic,
  cryptography/Fernet, HTTPX, PyYAML and pytest.
- **Agent models:** provider abstraction with Gemini 2.5 Flash as the primary live
  provider, Groq as an optional secondary provider and a deterministic scripted
  provider for tests. Keep pricing, tokens, latency and cost telemetry per call.
- **Tool protocol:** official Python MCP SDK pinned below major version 2; separate
  core-banking and CRM MCP servers plus a gateway that can use stdio locally and a
  clearly labelled in-process transport in serverless environments.
- **Database and identity:** Supabase Postgres, Auth, PostgREST and row-level
  security. Use SQL migrations; do not rely on manual dashboard-only schema steps.
- **Frontend:** Next.js 15 App Router, React 19, TypeScript, accessible semantic HTML,
  responsive CSS, Supabase browser authentication and Playwright.
- **Deployment:** one-origin Vercel Services configuration routing `/api/*` to
  FastAPI and all other paths to Next.js. Keep the continuous SLA worker separate.
- **Documents:** RFC822 `.eml`, PDF evidence, native multimodal/vision OCR fallback,
  WebVTT captions and exportable FMOS PDF packs.

Create reproducible lockfiles and pinned compatible dependency ranges. Do not copy
secrets into source files, test fixtures, chat messages, screenshots or build logs.

## Required repository structure

Create at least this structure, adding focused modules where useful:

```text
.
├── api/
│   ├── agents/          base, firewall, intake, classifier, verifier,
│   │                    resolver, communicator, supervisor, orchestrator, axiom
│   ├── kernel/          rules, SLA, gates, signed tickets, hash chain, lint,
│   │                    policy composer
│   ├── llm/             provider abstraction, Gemini, Groq, scripted provider,
│   │                    pricing and smoke tests
│   ├── mcp_tools/       matching engine, gateway and tool clients
│   ├── db/              PostgREST client, migrations/bootstrap, seed and integrity
│   ├── security/        encryption, masking and prompt redaction
│   ├── corpus/          deterministic RFC822/PDF generator
│   ├── tests/fixtures/eml/
│   ├── jobs.py          single-worker SLA scheduler
│   └── main.py          FastAPI application
├── mcp_servers/         core_banking_server.py and crm_server.py
├── rule_packs/          seven versioned YAML policy packs
├── supabase/migrations/ ordered SQL migrations with RLS/privilege hardening
├── dashboard/           Next.js application, components, scripts and Playwright
├── evals/               deterministic and live evaluation runners/reports
├── submission/          project copy, deck, cover, demo, proof and checklist
├── proof/               genuine evidence register; never fabricated
├── vercel.json
├── .env.example
├── README.md
├── DEPLOYMENT.md
├── STAKEHOLDER_GUIDE.md
├── STAKEHOLDER_READINESS_REVIEW.md
├── SUBMISSION.md
├── PROGRESS.md
└── buildlog.md
```

Keep the compliance kernel deterministic and LLM-free. Shared types and contracts
must make it impossible for the model layer to call financial posting directly.

## Core data model and lifecycle

Create migrations, typed application models and RLS policies for at least:

- cases, encrypted intake records and masked public identifiers;
- append-only case events with sequence, previous hash and current SHA-256 hash;
- per-case model-call telemetry;
- verification evidence and MCP receipts;
- signed authorization decisions and balanced journal entries;
- app users, roles and controlled invitations;
- stakeholder settings plus a separate append-only settings chain;
- Axiom plans/execution receipts;
- policy packs, proposals, replay results and versioned apply/reject events;
- public live-demo reservations, rate limits and persisted proof tokens;
- quarantine records, proactive alerts and customer tracking tokens.

Use an explicit legal state machine. The happy path must progress through received,
intake, classification, verification, governed financial resolution and customer
communication. Quarantine, human review, rejection and request-for-information are
first-class states, never UI-only labels.

Seed a wholly fictional Malaysian bank environment with accounts, transactions,
complaint history and a small detectable fraud ring. The public live fixture should
use a fictional Ahmad email, masked account suffix `6890`, merchant `TECHWORLD KL`
and an unauthorized RM2,450 card transaction. Provision the fixture atomically so
every public run receives a unique transaction reference and case reference.

## Required agent pipeline

Create and prove these modules and contracts:

- `api/agents/base.py` — `AgentContext`, `Event`, per-case telemetry-wrapped model calls.
- `api/agents/firewall.py` — deterministic prompt-injection firewall before any LLM.
- `api/agents/intake.py` — RFC822 email, PDF/native vision, deterministic extraction,
  PII encryption and prompt redaction.
- `api/agents/classifier.py` — model category/confidence proposal; urgency and SLA
  owned by the active rule pack.
- `api/agents/verifier.py` — MCP gateway producing exactly `PASS`, `FAIL` or
  `MANUAL_REVIEW` with evidence.
- `api/agents/resolver.py` — deterministic gate, signed authorization ticket,
  balanced double-entry `post_adjustment`.
- `api/agents/communicator.py` — customer draft, deterministic lint/repair,
  mandatory disclosures and authorized send.
- `api/agents/supervisor.py` — SLA monitoring and breach forecasting.
- `api/agents/orchestrator.py` — legal state transitions and one continuous SHA-256
  event chain across the complete case.
- Axiom — natural-language capability planning with role checks, visible effects,
  confirmation for writes and durable receipts. Axiom must not have direct money-
  movement authority.

The acceptance path must prove:

`one .eml → PASS → signed balanced adjustment → FINANCIALLY_RESOLVED → COMMUNICATED`

It must also prove the complete hash chain and balanced journal, with PII absent
from model prompts and public event payloads.

Axiom must map natural language only to an allow-listed capability. Its plan must
display the normalized command, caller role, whether state changes, expected side
effect, active gates and expected receipt before execution. Reparse writes on the
server, require explicit confirmation and issue a stable `AXR-...` receipt. Refuse
unknown capabilities and injection-shaped commands before any model call.

Policy Studio must implement: plain-English instruction → typed policy intent →
protected allow-listed diff → replay against the 200-case corpus → Compliance
apply/reject → versioned rule-pack and append-only policy chain. Immutable identity,
compliance vocabulary, posting authority and audit fields must never be editable
through natural language.

## Deterministic controls

The following must be enforced by code and tests, not prompt wording:

- Models cannot mint posting tickets.
- Money moves only after `PASS` evidence.
- Posting tickets are scoped, signed and expiring.
- Debit must equal credit.
- Low confidence routes to a person.
- Dual-control thresholds cannot be bypassed by one approver or duplicate approvers.
- Working-day SLA and urgency come from versioned policy packs.
- Mandatory BNM/FMOS language cannot be removed by the model.
- Prompt injection is blocked before a model call.
- Every case transition is hash chained and tampering identifies the broken link.
- Settings and governed agent actions are role checked and auditable.

## Case Study 1 coverage

Confirm all seven dispute categories and the handbook’s stated mix:

- Unauthorized transactions — 35%
- Billing errors — 22%
- Mis-selling — 18%
- ATM/debit card — 12%
- Insurance/takaful — 6%
- Loan/financing — 5%
- E-money/digital payments — 2%

Support English and Bahasa Malaysia, BNM/FMOS working-day obligations, compliant
customer communication, evidence-backed MCP verification, controlled financial
posting, real-time operational visibility and measurable evaluation.

Make the packs materially different, not copied labels. At minimum:

- Unauthorized transaction: reversal, automatic ceiling around RM3,000 and dual
  control above the threshold.
- Billing error: credit adjustment, repeat-complaint urgency, amount tolerance and
  mandatory fee amount in the response.
- Mis-selling: no automatic approval, higher confidence floor, formal register and
  prohibited victim-blaming language.
- ATM/debit card: part-dispensed-cash tolerance, skimmed-card urgency and mandatory
  card-block advice.
- Insurance/takaful: no automatic approval, high urgency for declined claims and
  clause citation on rejection.
- Loan/financing: mandatory CCRIS correction disclosure where relevant.
- E-money/digital: zero matching tolerance, recall-window urgency, NSRC `997`
  direction and no promise that funds will certainly be recovered.

All seven packs must define working-day SLAs, confidence floors, PASS-only posting,
bilingual communication requirements, the FMOS six-month referral window and a
category-specific GL suspense account. Validate packs at load time so unknown keys
or impossible outcome vocabulary fail loudly.

## Data, authentication and onboarding

- Use Supabase for persistent records, authentication and row-level security.
- Encrypt sensitive identifiers and mask them at tool/API boundaries.
- Keep public self-registration closed.
- Provision one controlled first Admin.
- The Admin adds staff from **Operators** using full name, work email and one least-
  privilege role: `OPS`, `INVESTIGATOR`, `COMPLIANCE` or `ADMIN`.
- Invitation links must lead to secure password setup.
- Settings must let authorized stakeholders manage bank identity, complaints
  contact, timezone, SLA warning horizon, default workspace, Axiom availability and
  the automatic-resolution kill switch.
- Never commit credentials, tokens, customer PII or production secrets.

## Required FastAPI surface

Implement authenticated authorization at the API/database boundary, not only in the
browser. Provide typed request/response schemas and tests for at least:

```text
GET    /health
POST   /demo/live
GET    /demo/live/latest
GET    /demo/live/{token}
GET    /auth/config
GET    /admin/users
POST   /admin/users/invite
GET    /settings
PUT    /settings
GET    /assistant/receipts
POST   /assistant/plan
POST   /assistant/execute
POST   /intake
POST   /intake/workbuddy
POST   /intake/proactive
GET    /proactive/{token}
POST   /proactive/{token}/respond
GET    /cases
GET    /cases/{case_ref}
GET    /analytics/overview
GET    /fraud/rings
GET    /quarantine
GET    /audit/{case_ref}/verify
GET    /cases/{case_ref}/fmos-pack
POST   /review/{case_ref}
GET    /events/stream
GET    /policy/packs
GET    /policy/proposals
GET    /policy/proposals/{proposal_id}
POST   /policy/compose
POST   /policy/proposals/{proposal_id}/apply
POST   /policy/proposals/{proposal_id}/reject
GET    /track/{token}
```

The public live endpoints must be rate limited, accept only a server-owned
allow-listed fixture and persist a signed/shareable proof. Arbitrary public RFC822,
PDF or PII upload is forbidden. Authenticated intake may accept raw RFC822 or
multipart PDF evidence. WorkBuddy intake must use its own scoped token.

## Required dashboard routes

Build complete, navigable and responsive pages for:

```text
/                     public live-first overview
/live                 one-action execution and evidence rail
/login                Supabase work-email sign-in
/set-password         invitation password setup
/simple               exception-focused complaints workspace
/pro                  Mission Control and pipeline oversight
/case/{case_ref}      evidence, decisions, journal, costs and event chain
/review               keyboard-friendly human decision queue
/theater              incremental agent/event visualization
/policy               natural-language Policy Studio and replay evidence
/radar                fraud-ring view
/audit                chain verification and tamper demonstration
/quarantine           pre-LLM injection evidence
/settings             stakeholder Control Register
/admin/users          Operators invitation and least privilege
/proactive/{token}    proactive suspicious-transaction confirmation
/track/{token}        public customer outcome tracker
```

If naming a route differently, preserve the same capability and document the map.
All rehearsal data must be visibly labelled and mutation-free. Live and rehearsal
states must never be merged in one ambiguous screen.

## UI/UX quality bar

The interface must be understandable without a technical presenter.

- A new visitor sees one primary action and an honest synthetic-input/live-execution
  boundary.
- Do not begin with a confusing dashboard tour.
- Show progress while a live run is executing; never silently swap in fixture results.
- After completion, expose case reference, outcome, model receipts, MCP receipts,
  deterministic gates, journal, chain status and a shareable proof link.
- Keep staff tools secondary until the live outcome is understood.
- Simple mode shows only exceptions requiring a person.
- Pro mode shows operational pressure, pipeline state, SLA forecast and system health.
- Mobile and desktop must have no horizontal overflow or clipped primary actions.
- Use accessible landmarks, labels, focus states, keyboard interaction, reduced-motion
  support and non-colour status indicators.
- Create a distinctive **Security Print** visual system and use it consistently:
  mineral-paper backgrounds near `#E7ECE7`, deep ink near `#0B0F0C`, controlled
  crimson near `#8B2333` for risk/actions and institutional green near `#2F684A`
  for verified states. Use Instrument Sans for interface typography and Martian Mono
  for receipts/microtype where licensing and the build environment allow.
- Use crisp rules, document/register layouts, restrained guilloche linework,
  endorsement stamps, microtype labels and explicit VOID/tamper states. Do not use
  generic gradients, glass cards, excessive rounding, random decorative imagery,
  giant shadows or unrelated design styles.
- Brand the operating agent as **Axiom by CaseZero**. Its interface is an inspectable
  action docket, not a floating generic chatbot bubble.

## Real integrations and deployment

- Verify real MCP protocol behavior for core-banking and CRM tools.
- Use in-process MCP only where serverless deployment requires it and label the
  transport honestly.
- Keep an always-on SLA supervisor as a separate single worker, not one scheduler per
  web replica.
- Verify Supabase migrations, RLS and privilege hardening.
- Verify the one-origin Vercel deployment for Next.js and FastAPI.
- Open the public URL in a clean browser session and test the complete live flow.
- Record the deployment ID, production URL, health response and a persisted proof URL.
- Do not claim “live bank production” until real bank credentials, mailbox transport,
  compliance approval and production security approval exist.

Complete all credential-free work before asking me for inputs. For the deployable
synthetic pilot, the only legitimate external inputs are normally:

- the handbook PDF if it is not already attached;
- permission to create/use a Supabase project and its URL/anon/service credentials;
- at least one live model API key, preferably Gemini;
- generated encryption, ticket-signing and WorkBuddy secrets entered through a
  local secret file or deployment secret manager, never pasted into source;
- authenticated GitHub and Vercel access if I authorize publishing;
- the first Admin’s fictional-demo or real bank work email for controlled onboarding;
- team/presenter/contact details and genuine CodeBuddy/WorkBuddy screenshots for the
  final hackathon form.

Real customer rollout additionally requires bank-owned core/CRM endpoints and field
mapping, complaint-mailbox and approved sender credentials, compliance approval for
all packs/templates, brand/domain/legal approval and one always-on SLA worker host.
Keep these separate from hackathon readiness.

When the public case completes, the proof view and JSON must show at least:

- fresh/reused execution status, runtime, duration and case reference;
- sanitized input metadata and masked account;
- final case status, category, urgency, confidence and outcome;
- verification result and whether posting occurred;
- ordered stage receipts with actor, event type, sequence, timestamp and event hash;
- actual model provider/model, token counts, latency, cost and agent name;
- actual MCP server/tool, transport, latency and success result;
- journal debit, masked credit, amount, posting actor and balanced state;
- chain length, validity, head hash and exact first bad sequence if invalid.

The UI must show an honest failure if any required live service fails. A separately
labelled “open latest completed proof” recovery is allowed; silently replacing the
failed run with demo data is not.

## Corpus and measurable evaluation

Generate a deterministic labelled corpus of **200 RFC822 complaints** and **20 PDF
statements**. Match the seven-category distribution exactly as 70/44/36/24/12/10/4.
Include English and Bahasa Malaysia, digital PDFs, scan-like PDFs and phone-photo-
style PDFs. Include at least five prompt-injection attacks while keeping clean cases
free of attack text.

Build deterministic and live evaluation runners. Measure and persist category
accuracy, urgency accuracy, injection true/false positives, run errors, p50/p95 model
latency, tokens and ringgit cost per case. Never invent a target result or hardcode a
metric into the dashboard. The dashboard and deck may display only the latest
persisted run, clearly labelled with its evaluation mode and date.

Create reproducible synthetic fixtures for MCP and agent smoke tests. Test fixtures
must include a `FakeDatabase`, a prompt-recording scripted LLM provider and checked-
in `.eml` files for happy path, low confidence, failed verification and injection.

## Verification requirements

Run the complete relevant suite and report exact results:

```bash
cd <repository-root>
.venv/bin/python -m pytest api/tests -q
.venv/bin/python -m api.agents.smoke
.venv/bin/python -m api.mcp_tools.smoke
.venv/bin/python -m api.llm.smoke
.venv/bin/python -m api.db.verify_integrity
cd dashboard
npm run typecheck
npm run build
npm run test:e2e
npm audit --audit-level=high
```

On Windows, use the equivalent `.venv\Scripts\python.exe` commands. If credentials
are unavailable, complete the deterministic/offline suite first, report the live
checks as blocked, create `.env.example`, and ask only for the missing Supabase/model/
deployment values. Rerun the live checks after credentials are supplied.

Do not pad the suite to reach a predetermined test count. Coverage must be comparable
to the system surface and every control claim must have a named failing test. Report
the actual number of passing tests and never repeat a number from this prompt or a
previous machine unless the current run produced it.

Also hard-test at least these negative paths:

- Prompt injection is quarantined before any model call.
- `FAIL` and `MANUAL_REVIEW` cannot post money.
- Forged, expired or incorrectly scoped tickets are refused.
- An unbalanced journal is refused.
- Low confidence reaches the human queue.
- Unauthorized roles cannot invite users, change settings or approve governed work.
- A broken hash-chain link is identified exactly.
- Public callers cannot upload arbitrary customer email or PII.
- Provider/API failure produces an honest error, never a fake success.
- Desktop and mobile layouts remain usable.

## Submission package

Read the handbook’s submission order and ensure that `submission/` contains:

1. Project title, under-10-word blurb and complete description.
2. A rubric-ordered 16:9 PPTX and matching PDF with readable speaker notes.
3. The required 380×216 cover.
4. A clear 5–8 minute narrated 1080p demo with captions.
5. A run-of-show aligned to the rubric and live proof.
6. A manifest with exact sizes and SHA-256 hashes.
7. A final checklist and owner handoff.
8. Clearly marked locations for genuine CodeBuddy and WorkBuddy evidence.

The deck and film must use real application screenshots and verified evidence. Do
not generate decorative images that make the product harder to understand. Inspect
every slide/page and a video contact sheet before calling them complete.

Use a concise 10-slide stakeholder narrative:

1. Axiom / AI Agent Track / Case Study 1 / one governed outcome.
2. Starting point: 1.8M customers, 90 minutes, 11% deadline misses, 5–20 working days.
3. One sanitized complaint becomes public production proof.
4. Six agents propose while the deterministic kernel and MCP evidence decide.
5. PASS-only financial control, signed ticket, RM amount on both journal sides and
   verified chain.
6. One-click live user experience with no fake success fallback.
7. Plain-language customer resolution and required FMOS path.
8. Measured release evidence from actual tests/evaluation/live execution.
9. Controlled rollout beginning with unauthorized transactions and billing errors
   (57% of the stated mix), with shadow mode and compliance sign-off.
10. Exact bank-owned handoffs: core/CRM, mailbox/sender, policy approval, identities,
    domain and always-on worker.

Keep text large and minimal. Use real screenshots at readable scale. Add speaker
notes with source references. Render and inspect every slide and every PDF page;
run overflow/layout checks before finalizing. The video should follow the same story,
show one actual public execution early, use visible cursor/click feedback, include
narration and WebVTT captions, and stay inside the handbook’s 5–8 minute window.

## Evidence integrity

This CodeBuddy conversation is itself genuine evidence of the work performed in
this session. Preserve it honestly.

- Do not fabricate CodeBuddy/WorkBuddy history, timestamps or screenshots.
- If starter files existed, do not claim CodeBuddy authored work that predates this
  session. If the folder was empty, preserve the Git history proving the greenfield
  sequence.
- Do not edit screenshots to simulate product activity.
- Synthetic product data is acceptable only when clearly labelled.
- Keep a running record of files inspected, changes made, commands run, outputs,
  deployments and unresolved external dependencies.
- Update `PROGRESS.md`, `README.md`, `buildlog.md`, submission documentation and the
  manifest whenever your work materially changes the verified state.

## Working behavior

- Work autonomously until the evidence-backed requirements are complete or a true
  external blocker remains.
- Use connected GitHub, Supabase and Vercel tools/plugins when available. If they are
  not installed or authenticated, prepare the exact local configuration and ask for
  the minimum login/authorization only when deployment becomes the active phase.
- Make reasonable, reversible assumptions and state them.
- Preserve unrelated user changes and never delete unknown files.
- Do not expose secrets in chat or command output.
- Ask me only for information that cannot be discovered locally and materially
  blocks progress.
- Keep explanations understandable to a non-technical banking stakeholder.
- After each major phase, give a short progress update with evidence.

Execute in this order and do not skip verification between phases:

1. Handbook/rubric extraction, architecture, repository initialization and docs.
2. Deterministic kernel, seven rule packs and named invariant tests.
3. Supabase schema/RLS, encryption, seed data, MCP servers and signed tickets.
4. Six-agent pipeline, Axiom, RFC822/PDF intake and end-to-end acceptance tests.
5. FastAPI authorization boundary, live proof endpoints and SLA worker.
6. Security Print dashboard, onboarding, Simple/Pro operations and responsive QA.
7. Corpus, evaluation, negative/security hard tests and FMOS export.
8. Production configuration, Supabase migration, Vercel deployment and clean-browser
   live proof.
9. Rubric-ordered submission deck, cover, 5–8 minute demo, captions, manifest and
   owner handoff.
10. Final test rerun, documentation reconciliation, intentional Git commit/push and
    evidence-backed report.

Commit at coherent milestones with descriptive messages if Git authorization is
available. Never commit secrets, raw real-customer data, temporary browser videos,
Office lock files or generated scratch directories.

## Final response format

When finished, report:

1. Stakeholder outcome and whether the system is sufficient for Case Study 1.
2. What already existed versus what you changed in this CodeBuddy session.
3. Production URL, deployment status and persisted live-proof URL.
4. Exact test/build/security results.
5. Case Study 1 and rubric coverage matrix.
6. Submission artifact paths.
7. Remaining items required from me for the hackathon submission.
8. Separate bank-owned requirements for real customer rollout.
9. Git branch/commit/PR status, if authorized and performed.

Never hide a failed check. If something remains incomplete, state exactly why,
what was attempted and the safest next action.

---

When taking screenshots for the submission, capture the actual CodeBuddy prompt,
its repository audit, a real implementation or verification step, test output, and
the final evidence-backed handoff. Do not stage or manufacture a conversation.
