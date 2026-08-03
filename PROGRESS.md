# CaseZero — Build State & Handoff

**Read this first in a fresh session.** `MASTERPLAN.md` is the *design*; this file is
the *state*. Where they disagree, this file is right.

Last verified: **4 Aug 2026, 01:59 UTC+8**
Repo root: `/Users/saminsmac/Projects/tencent copy 2`
Code root: `casezero/`

---

## 0. Environment — read before running anything

Three things will waste an hour each if you miss them.

| Gotcha | What to do |
|---|---|
| **Two Pythons on this machine.** The system `python` (3.11, Homebrew) does **not** have `supabase` installed. The venv (3.13) has everything. | Always run `.venv/bin/python`, never bare `python`. |
| **`timeout` does not exist** in this zsh. | Don't prefix commands with `timeout`; it fails with `command not found`. |
| **MCP SDK 2.0 breaks FastAPI.** `mcp>=2` requires `starlette>=1.0`; installing it silently downgrades the web stack. | `requirements.txt` pins `mcp>=1.9,<2`. Do not relax it. |

```bash
cd "/Users/saminsmac/Projects/tencent copy 2/casezero"

.venv/bin/python -m pytest api/tests -q          # 453 tests, ~7s
.venv/bin/python -m api.agents.smoke             # live six-agent E2E, 6 checks
.venv/bin/python -m api.mcp_tools.smoke          # MCP over real stdio, 6 checks
.venv/bin/python -m api.llm.smoke                # Gemini + Groq + vision OCR gate
.venv/bin/python -m api.db.verify_integrity      # live tamper-evidence demo
```

Secrets live in `casezero/.env` (git-ignored, and the root `.gitignore` also covers
the top-level `.env`). Supabase project `jipzxjbdsvlcbxemqqyj`, region
`ap-northeast-2`.

**Postgres wire protocol is blocked on this network.** Everything goes over HTTPS:
DDL via the Supabase Management API (`api/db/management_api.py`), data via PostgREST
(`api/db/client.py`). Do not reintroduce `asyncpg`/`psycopg2` connection attempts.

---

## 1. What is built and verified

### 1.1 Compliance kernel — deterministic, LLM-free

| File | What it owns | Tests |
|---|---|---|
| `api/kernel/sla.py` | Malaysian working-day arithmetic, public holidays, cutoffs, breach forecast | 20 |
| `api/kernel/chain.py` | SHA-256 hash-chained audit events; reports the **exact** row that was altered | 17 |
| `api/kernel/rules.py` | Rule-pack loader, immutability contract, disclosure contract, condition evaluator, validation | 95 |
| `api/kernel/lint.py` | FMOS clause inserted by control flow; mandatory disclosures; prohibited phrases | 33 |
| `api/kernel/gates.py` | State machine, confidence floor, PASS-only money movement, dual control | 45 |
| `api/kernel/tickets.py` | HMAC-signed authorisation tickets — the gate's ruling survives leaving the process | 17 |

**280 kernel tests, all passing.** No network, no model calls, no flakes.

Three invariants worth quoting on stage, each proven by a named test:

- `FINANCIALLY_RESOLVED` is unreachable unless `verification_result == PASS`.
- A classification below the pack's confidence floor routes to a human, never to a payout.
- Above the dual-control threshold one approver is refused, and the same person cannot be both approvers.

**Two anti-silent-failure guards** added in `rules.validate()` — both matter because a
compliance check that always passes is worse than no check:

- A disclosure declaring an unsupported key (e.g. `must_state_amount_rm`, one character off) is a **load-time error**, not a silently-passing rule.
- A disclosure or FMOS clause naming an outcome the `case_outcome` enum cannot produce is rejected. (This is why packs say `RESOLVED_IN_FULL`, not `RESOLVED`.)

### 1.2 Rule packs — all seven categories live

`casezero/rule_packs/*.yaml`, volumes mirroring the brief exactly:

| Pack | Volume | What makes it different (not copy-paste) |
|---|---|---|
| `unauthorized_transaction` | 35% | REVERSAL; auto ≤ RM3,000; dual control > RM3,000 |
| `billing_error` | 22% | CREDIT_ADJUSTMENT; repeat-complaint ⇒ High; 0.5% tolerance; must state the fee in figures |
| `mis_selling` | 18% | **auto_approve = 0** — never auto-resolves; 0.85 confidence floor; formal register; blocks "you signed the documents" |
| `atm_debit_card` | 12% | 10% tolerance (part-dispensed cash); live skimmed card ⇒ High; card-block advice mandatory |
| `insurance_takaful` | 6% | auto_approve = 0; declined claim ⇒ High; must cite the clause on rejection |
| `loan_financing` | 5% | **CCRIS correction disclosure** — refunding the charge while leaving the credit record wrong is not a resolution |
| `emoney_digital` | 2% | 0% tolerance; recall-window ⇒ High; must direct customer to NSRC **997**; blocks "we will recover your funds" |

Held to the brief by `TestEveryShippedPack`: shares sum to 1.00, SLA is 5/20/20 in
every pack, every pack is PASS-only, bilingual, carries the 6-month FMOS window, and
has its own GL suspense account.

### 1.3 Two real MCP servers — verified over stdio

`mcp_servers/core_banking_server.py` and `mcp_servers/crm_server.py`, built on the
official SDK's `FastMCP`. Tools are **discovered** by the client, not hardcoded.

```
core-banking: get_account, list_transactions, find_transaction,
              verify_claim, post_adjustment, get_ledger
crm:          get_customer_by_account, get_customer,
              get_complaint_history, get_case_facts
```

`api/mcp_tools/smoke.py` output (all 6 PASS, run against live Supabase):

1. Both servers complete an MCP `initialize` and advertise their tools.
2. `get_account` returns `******6890` — masked *at the tool*.
3. `verify_claim` → `PASS` on `TXN20260728AHMAD`.
4. `get_case_facts` → `segment=retail repeat=False`.
5. **Posting with a forged ticket is refused by the server.**
6. **A RM1 ticket presented for RM9,000 is refused.**

That last pair is the answer to *"what stops your agents refunding everything?"* — it
is not the prompt, it is a signature the agent cannot produce.

Supporting layers: `api/mcp_tools/matching.py` (the PASS/FAIL/MANUAL_REVIEW engine,
24 tests), `api/mcp_tools/gateway.py` (stdio transport with a recorded in-process
fallback so a subprocess failure mid-demo degrades instead of dying).

### 1.4 Everything else already standing

- **Schema live on Supabase** — `001_init.sql` (enums in the brief's exact vocabulary, tables, RLS) + `002_audit_hardening.sql` (privilege revocation making `case_events` append-only while preserving `ON DELETE CASCADE`, immutable `rule_packs.yaml` trigger, 4 analytics RPCs).
- **Tamper-evidence proven live** — `api/db/verify_integrity.py`: the service role is refused by Postgres privileges, and a table-owner tamper is caught by `verify_chain` at the exact event.
- **LLM layer** — `api/llm/`: Gemini 2.5 Flash (+ native vision OCR, no tesseract anywhere), Groq Llama 3.3 70B, Hunyuan stub. Per-call tokens/latency/ringgit cost. Block 0 gate passed 3/3 including exact PDF transcription.
- **Data layer** — `api/db/client.py` (PostgREST, service-role vs user-JWT split), `api/security/crypto.py` (Fernet + masking + `redact_pii` before prompts), `api/db/seed.py` (8 accounts, 23 transactions, an 8-transaction fraud ring).
- **Corpus** — `api/corpus/generate_v1.py` deterministically generates 200 labelled
  RFC822 complaints and 20 statement PDFs; `statement_pdf.py` owns the three visual
  variants (digital, scan-like and phone-photo).

### 1.5 Six-agent pipeline — complete and live-verified

| File | What it owns |
|---|---|
| `api/agents/base.py` | `AgentContext`, chain `Event`, PII-redacted and database-persisted per-case model telemetry |
| `api/agents/firewall.py` | Deterministic prompt-injection screen before any model call; concealed/base64/role/tool attacks included |
| `api/agents/intake.py` | RFC822 parsing, deterministic money/account/reference extraction, PDF text + Gemini vision fallback, PII encryption |
| `api/agents/classifier.py` | Model category/confidence proposal; rule-pack urgency, confidence floor and working-day SLA |
| `api/agents/verifier.py` | MCP evidence collection and exact `PASS` / `FAIL` / `MANUAL_REVIEW` vocabulary |
| `api/agents/resolver.py` | Deterministic gate, signed ticket minting, balanced `post_adjustment` |
| `api/agents/communicator.py` | Draft sections, deterministic lint repair, FMOS insertion, send authorisation |
| `api/agents/supervisor.py` | SLA watch, breach forecast and escalation events |
| `api/agents/orchestrator.py` | Legal status transitions and one continuous SHA-256 chain across every stage |

**453 total tests, all passing.** Fixtures include a real-chain `FakeDatabase`, a
prompt-recording scripted provider, and four checked-in RFC822 files under
`api/tests/fixtures/eml/`. The acceptance test replays `happy_path.eml` and proves
`PASS` → signed balanced reversal → `FINANCIALLY_RESOLVED` → `COMMUNICATED`, with
PII absent from both prompts and event payloads.

`api.agents.smoke` was rerun after the final telemetry change on 4 Aug 2026. It
created `MYB-2026-000012`, posted an authorised RM890 reversal, verified all 13
chain links against Supabase, then created `MYB-2026-000013` and quarantined it
before any model call. All six checks passed. A direct PostgREST check found the
three expected `llm_calls` rows (`intake`, `classifier`, `communicator`) bound to
the resolved case, totalling the same RM0.008713 reported by the run.

### 1.6 FastAPI boundary — complete and offline-verified

`api/main.py` now exposes the production-shaped HTTP surface: authenticated raw
RFC822/multipart intake, token-authenticated WorkBuddy intake, proactive intake,
RLS-backed case list/detail, governed `APPROVE` / `REJECT` / `REQUEST_INFO`, public
magic-link tracking, Admin-only work-email invitation/listing, and the ephemeral
SSE stream used by Agent Theater. The MCP
gateway closes through the FastAPI lifespan.

Authentication lives in `api/web/auth.py`: Supabase validates the bearer token,
then the caller's `app_users` row is read with that JWT. Dashboard reads construct
a PostgREST client with the same JWT, so RLS—not the UI—filters cases. Case responses
strip both encrypted PII fields and expose only the masked account suffix.

Human approval uses `api/review.py` and the same deterministic gates and signed
posting ticket as the autonomous path. The gate now distinguishes the auto-approval
ceiling from the review band: a human can confirm low-confidence or above-ceiling
PASS evidence, while dual control and the PASS-only invariant remain mandatory.

`api/tests/test_api.py` proves auth refusal, `.eml` intake, ciphertext stripping,
case detail/chain/journal/cost, WorkBuddy token refusal, human resume, and the
SLA-aware request-info path. `api/tests/test_invitations.py` additionally proves
normalisation, duplicate refusal and role validation before an Auth identity is
created. Full suite: **453 passed, zero warnings**.

### 1.7 Dashboard and Security Print design system — complete and verified

`casezero/dashboard/` is a Next.js 15 / React 19 PWA-shaped application with a
purpose-built **Security Print** visual language: paper and ink tokens, guilloche
linework, endorsement stamps, microtype rules, punched SLA strips and a VOID
tamper state. It deliberately uses no gradients, glass, shadows, or generic rounded
dashboard cards. Instrument Sans and Martian Mono are loaded through `next/font`.

All planned operational surfaces now exist: a themed first-visit judge guide,
Supabase login plus an explicitly labelled offline rehearsal, Admin Operators and
single-use password setup, Simple mode, Pro Mission Control, Agent Theater, case
detail with rule-key “Why?” evidence, keyboard review queue, Policy Studio, Fraud
Radar, Audit Explorer, quarantine proof, and the public customer tracker. The
rehearsal mode is synthetic and mutation-free; it is never presented as live data.

Verification on 4 Aug 2026:

- `npm run typecheck` — clean.
- `npm run build` — clean, 15 application routes generated.
- `npm audit` — **0 vulnerabilities** after pinning the current `postcss` and
  `sharp` fixes through package overrides.
- In-app browser smoke — login → offline rehearsal, Simple mode and Pro mode all
  rendered; DOM/landmark inspection passed; console had **0 warnings/errors**.
- Responsive smoke at 390×844 — critical content and actions remained reachable;
  nav degrades to a horizontally scrollable labelled register; no console errors.
- Reduced-motion rules, visible focus, skip-link, semantic headings/form labels and
  non-colour status labels are present in the shared design system.
- The public `/` route explains the full five-stop judging path. The judge button
  needs no email, sets mutation-free rehearsal mode, and opens a persistent guided
  callout. Admins invite real staff from `/admin/users`; recipients land on
  `/set-password`, while Postgres RLS remains the authorisation boundary.

### 1.8 Policy Composer — complete, versioned and live

`api/kernel/composer.py` turns a plain-English instruction into a typed
`PolicyIntent`, then applies a deterministic allowlist before the proposal can touch
configuration. Immutable identity, compliance and posting paths are refused;
invented paths are refused; threshold relationships and the full governance schema
are validated. Each proposal includes a DeepDiff JSON patch, a human-readable diff,
a 200-case replay simulation and explicit risk flags.

The API exposes compose, inspect, apply and reject endpoints. Migration
`003_policy_composer.sql` adds an append-only policy event chain and an atomic
`activate_rule_pack` database function. All seven version-1 packs are active in the
live project, and `AgentContext` loads the active database version for future cases.
The dashboard Policy Studio performs the real compose/apply/reject workflow; its
offline rehearsal remains clearly synthetic and mutation-free.

### 1.9 Evaluation corpus and production model evidence — complete

`corpus/v1/` contains exactly **200** deterministic RFC822 complaints in the brief's
volume mix (70/44/36/24/12/10/4), with 100 English, 60 Bahasa Malaysia and 40
code-switched cases, five prompt-injection attacks and 20 A4 statement attachments.
The PDF set rotates digital, scan-like and phone-photo layouts; representative pages
from all three variants were rendered and visually inspected.

`evals/run.py` and `evals/report.py` provide reproducible deterministic and live
runs. The full 200-case Gemini production run completed with zero errors and was
persisted as eval run `f3951458-0998-44a4-9f21-d249035469fa`:

| Measure | Result |
|---|---:|
| Category accuracy | **95.90%** |
| Urgency accuracy | **98.97%** |
| Injection detection | **5 / 5**, zero clean false positives |
| Model latency | p50 **2,616 ms** · p95 **4,626 ms** |
| Model cost | **RM0.001025 / case** |

The deterministic baseline is explicitly labelled as a fixture baseline; it is not
presented as production model performance. `evals/latest.json` is the dashboard's
latest production evidence.

### 1.10 Beyond-spec surfaces — complete

- Live operations analytics and workload endpoints drive Pro Mission Control.
- Fraud-Ring Radar detects merchant/device clusters while masking accounts at the
  API boundary. The seeded ring spans eight accounts and RM18,215.
- Quarantine and Audit Explorer expose pre-model firewall decisions and exact-chain
  verification without disclosing encrypted PII.
- `api/reports/fmos_pack.py` generates a four-page Security Print referral pack with
  overview, decision, balanced journal, complete event timeline and chain proof.
- Migration `004_proactive_disputes.sql` plus the `/proactive/{token}` API and PWA
  implement token-bound customer confirmation. **Not me** launches the same governed
  pipeline; a FAIL/MANUAL result cannot move money.
- The service worker and manifest provide installable/offline rehearsal behaviour;
  the live authenticated Agent Theater consumes its SSE stream incrementally.

### 1.11 Final verification matrix — current

| Check | Result |
|---|---|
| Python suite | **453 passed** |
| Playwright browser acceptance | **8 passed** |
| Next.js typecheck and production build | **clean** |
| npm dependency audit | **0 vulnerabilities** |
| MCP protocol smoke | **6 / 6** |
| Gemini + Groq + vision smoke | **3 / 3** |
| Six-agent live smoke | **6 / 6**; `MYB-2026-000020` resolved, `MYB-2026-000021` quarantined |
| Live WorkBuddy HTTP intake | `MYB-2026-000016` communicated; FAIL safely blocked posting |
| Database tamper proof | service-role writes refused; owner tamper located at exact event |
| FMOS PDF visual QA | all four pages rendered, inspected, no clipping/overflow |

### 1.12 Operations and release packaging — complete

- `api/db/seed_users.py` idempotently creates the four synthetic staff identities,
  refuses a password under 12 characters and never prints it. Existing accounts are
  updated without producing duplicates.
- `api/jobs.py` runs the deterministic SLA supervisor as one dedicated worker. It
  deduplicates forecasts by MYT date and breach state; `--once` is the deploy smoke.
- Non-root API and standalone Next.js Dockerfiles, Compose stack and a labelled
  emergency rehearsal overlay are checked in. YAML validation passed; this host
  does not have Docker, so image execution remains a deployment-host check.
- `README.md`, `DEPLOYMENT.md`, `SUBMISSION.md`, `buildlog.md` and `proof/README.md`
  form the operator, release and judging handoff.
- `MOTION_AUDIT.md` and `WEB_INTERFACE_AUDIT.md` record the pre-remediation findings
  and approved release result. The final in-app browser DOM/visual check shows the
  intended Security Print surface with landmarks and content intact.
- Final live rerun: MCP **6/6**, Gemini/Groq/vision **3/3** (RM0.011373), agent
  pipeline **6/6**, database privilege/tamper proof passed, scheduler smoke passed.
- Vercel Services release files are present: root `vercel.json` publishes Next.js
  at `/` and FastAPI at `/api`, `api/pyproject.toml` declares the Python runtime,
  and `.vercelignore` excludes secrets, local environments and generated corpora.
  GitHub CLI is authenticated as `saminsarwat007`; Vercel CLI still needs a login.

---

## 2. What is left

No product-code or acceptance-test work remains. These owner/external-system actions
cannot be completed from the repository alone:

1. Authenticate the Vercel CLI once. The installed Vercel plugin supplies the
   deployment guidance, but it does not expose account credentials to the terminal.
2. After production gets its final URL, allow that origin and `/set-password` in
   Supabase Auth redirects, set `DASHBOARD_BASE_URL`, and redeploy.
3. Export the genuine CodeBuddy conversation history and WorkBuddy screenshots,
   record the demo, add team/presenter details and submit the form.
4. Optional physical-channel upgrades require Gmail, Telegram and VAPID credentials.
   The WorkBuddy channel and presenter-mode proactive PWA are already verified.

---

## 3. Invariants a fresh session must not break

1. **The kernel is LLM-free.** Models propose; `gates.py` disposes. Never call a model from `api/kernel/`.
2. **Money moves only on `PASS`**, only under a valid ticket, only double-entry.
3. **The FMOS clause is inserted by code, not requested in a prompt.** `lint_outbound` repairs; `authorize_send` blocks.
4. **Spec vocabulary is verbatim** in UI and code: `PASS` / `FAIL` / `MANUAL_REVIEW`, `FINANCIALLY_RESOLVED`, "governance schema", "urgency", "working days".
5. **Adding a category is configuration.** If a feature needs a code change per category, it is in the wrong place.
6. **PII never reaches a model.** `redact_pii` on the way out; masked at the tool boundary.
7. **Tests are the argument, not decoration.** Every compliance claim has a named test that fails if the claim stops being true.

---

## 4. What I need from you

- Complete the one-time Vercel account login when prompted. No secrets need to be
  pasted into chat; the CLI opens Vercel's browser/device authorisation flow.
- Tell me only if the production project must belong to a particular Vercel team.
  Otherwise the authenticated account's personal scope is the default.

| Priority | What | Why |
|---|---|---|
| Required | A **12+ character demo staff password** | Creates the real OPS / INVESTIGATOR / COMPLIANCE / ADMIN logins without committing a default password |
| Required for public URL | Log in with `vercel login` or provide a Vercel token, and choose/provide access to an API host | This machine has the Vercel CLI but no session; the API and one scheduler worker also need hosting |
| Submission-critical | **Genuine CodeBuddy history export and WorkBuddy screenshots** | Tencent proof-of-use is mandatory and cannot be fabricated from code |
| Submission-critical | Team/member names, presenter name and final video/cover assets | Completes the form and judge-facing media |
| Optional | Gmail app password, Telegram bot token, VAPID key pair | Enables the non-essential physical mailbox/bot/push upgrades |
| Optional | Bank name/logo preference | The current synthetic identity is `MYBank Berhad` |

---

## 5. Quick file map

```
casezero/
  api/
    config.py              typed settings (+ MCP transport switch)
    kernel/                sla, chain, rules, lint, gates, tickets   ← LLM-free
    llm/                   provider, gemini, groq, hunyuan, pricing, smoke
    db/                    client (PostgREST), bootstrap, management_api,
                           seed, verify_integrity, migrations/
    agents/                firewall, six agents, supervisor, orchestrator, live smoke
    mcp_tools/             matching, core_banking, crm, gateway, smoke
    security/crypto.py     Fernet + masking + redact_pii
    corpus/                statement_pdf.py
    web/                   Supabase JWT/RLS auth + SSE hub
    main.py                FastAPI intake, cases, review, tracker, event stream
    tests/                 448 tests; fake DB + scripted LLM + `.eml` replay corpus
  mcp_servers/             core_banking_server.py, crm_server.py  ← real MCP, stdio
  rule_packs/              7 YAML packs
  .env                     secrets (git-ignored)
```
