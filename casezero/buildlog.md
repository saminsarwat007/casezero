# CaseZero Build Log

All implementation dates are 2026 and all bank/customer data is synthetic.

## 3 Aug — foundation and governed vertical slice

- Established Supabase schema, RLS, seven category packs and deterministic kernel.
- Added Gemini/Groq provider abstraction, telemetry and native PDF vision gate.
- Implemented core-banking and CRM MCP stdio servers with signed posting tickets.
- Completed email → verification → balanced adjustment → communication acceptance
  path and pre-model injection quarantine.

## 4 Aug — product depth and release closure

- Hardened append-only audit privileges and verified live tamper detection.
- Completed six-agent orchestration, human review, SSE, WorkBuddy intake and all
  operations/customer dashboard surfaces.
- Shipped Policy Composer with protected schema, 200-case simulation and versioned
  apply/reject chain.
- Generated corpus v1: 200 RFC822 complaints, 20 PDFs, exact category/language mix
  and 5 attacks. Ran the full live Gemini evaluation and persisted its measurements.
- Added live analytics, fraud-ring correlation, quarantine proof, proactive customer
  alert and four-page FMOS Referral Pack.
- Added four-role auth seeder, single-worker SLA scheduler, container packaging,
  deployment/submission runbooks and motion/web-interface audits.
- Added a Security Print first-visit guide, account-free safe rehearsal,
  Admin-only work-email invitations, least-privilege operator register and secure
  password setup. Prepared one-origin Vercel Services deployment for Next.js + FastAPI.
- Introduced **Axiom by CaseZero**, a deterministic, role-aware operating
  agent with inspectable plans, explicit confirmation and receipt logging.
- Added the stakeholder Control Register, a separate settings hash chain, a real
  automation kill switch and exact Supabase grants for the new tables.
- Rebuilt Pro for desktop/mobile, added a real mobile menu and stage selector, and
  removed clipping/overflow from the operational pulse and pipeline.
- Added a 1920×1080 Playwright recording script with a visible cursor, click ripple
  and safe stakeholder narrative for direct demo use.
- Promoted the verified Vercel Services artifact to
  `https://casezero-alpha.vercel.app`; public UI/API smoke and the production
  error/warning scan were clean.
- Replaced the confusing 60.8-second tour with a 5:55.77 narrated 1080p stakeholder
  film: 13 rubric-led chapters, visible cursor/click feedback, persistent captions,
  a WebVTT transcript and a 13-frame visual QA contact sheet.
- Rebuilt the 10-slide submission deck as **Axiom by CaseZero**: no generated mood
  imagery, real production UI and financial evidence only, rubric-ordered narrative,
  speaker notes, slide-by-slide visual inspection, verified PDF and exact 380×216 cover.
- Corrected the demo recorder to source its explanatory frames from the final Axiom
  render instead of the archived decorative deck, then repeated the public live capture.
- Release gates after the live-first rebuild: **466 backend tests**, **14 browser tests**,
  TypeScript, production build, dependency audit, MCP, LLM/vision, live agent,
  database-integrity and scheduler smokes all passed.

## 4 Aug — UX simplification and the stakeholder complaint composer

- Replaced the 11-item flat sidebar with three role-filtered groups in plain language
  (Operations / Compliance / Setup). Simple and Pro survive as the first two
  Operations entries, so the duplicate topbar mode switch is gone. Role filtering is
  a usability control only; RLS and per-endpoint `require()` still enforce authority.
- Added `GET /me` so the menu can hide pages a role cannot act on, and
  `dashboard/hooks/use-operator.ts` to consume it.
- Made the public runner accept a complaint the visitor writes themselves:
  `GET /demo/personas`, `POST /demo/compose` (multipart, optional PDF) and
  `GET /demo/live/{token}/progress` for stage-by-stage progress read from the hash
  chain while the request is still open. The composer and the fixture runner share
  one execution path (`_execute_public_run`).
- Added `api/security/public_intake.py`: the complaint must name an allow-listed
  synthetic account, and any other Malaysian account number or NRIC is **refused,
  not scrubbed**.
- Replaced Axiom's regex matcher with a two-layer agent: the model resolves phrasing
  the deterministic matcher cannot, and `build()` still decides role, confirmation
  and gates in code. `/assistant/execute` re-plans and refuses with 409 if its own
  re-read reaches a different action than the operator approved.
- Turned the Axiom docket into a conversation, with each governed docket bound to the
  message that produced it.
- Release gates after the composer work: **485 backend tests**, **17 browser
  journeys**, TypeScript, production build and `npm audit --audit-level=high`
  (0 vulnerabilities) all passed.

## External proof boundary

WorkBuddy intake is present in the production path and was exercised by a live HTTP
smoke. Genuine Tencent UI screenshots and CodeBuddy history must be exported by the
account owner; this repository does not fabricate them.
