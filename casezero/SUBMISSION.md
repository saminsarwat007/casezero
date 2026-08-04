# CaseZero — Submission Copy

## 1. Overview — target scenarios, users and value proposition

**Case Study 1: AI-Powered Banking Dispute Automation Pipeline.** CaseZero is an AI
Dispute Resolution OS for a Malaysian regional bank serving 1.8 million retail and
SME customers. It turns unstructured customer email and PDF evidence into a
verified, compliant, auditable outcome in minutes. The primary operator is a
non-technical complaints lead: Simple mode shows only what needs human attention,
while Policy Studio lets her change allowed automation thresholds in plain English.

Six agents intake, classify, verify, resolve, communicate and forecast SLA risk.
They do not control compliance or money. A deterministic kernel enforces confidence
routing, `PASS`-only posting, signed authorisation tickets, dual control, balanced
journals, working-day deadlines and mandatory FMOS disclosure.

**Axiom by CaseZero** is the stakeholder's governed operating agent. It accepts
natural language, but presents an action docket—not a conversational promise—with
the required authority, effect and safety gates. Reads may run immediately. Invites
and settings changes require an eligible role, explicit confirmation and a durable
receipt. The stakeholder Control Register supplies the operational kill switch and
keeps every change in a separate hash chain.

## 2. Real-world insights — pain source, audience and core problems

The case-study baseline is 90 minutes per complaint across multiple departments,
with 11% of regulatory deadlines missed. The customer experiences silence and
legalese; investigators manually assemble evidence; Compliance reviews every
letter; Operations cannot see cost per case; and a policy update waits for an IT
release. Raw account data flowing into a model is also unacceptable to bank IT.

CaseZero treats these as system-design problems. PII is encrypted and redacted,
Postgres RLS filters every staff read, prompt injection is quarantined before a
model call, and every state transition is an append-only hash-chain link. Low model
confidence fails safe to a human. The same governance path handles email,
WorkBuddy, manual `.eml` replay and a proactive customer alert.

## 3. Solution design — business, technical architecture and prompt use

The model layer is provider-independent (Gemini, Groq, Hunyuan-compatible stub) and
returns typed proposals. The Classifier prompt constrains output to the seven exact
category codes; the Communicator prompt drafts only the human-readable content;
FMOS text is inserted and linted by code. Core banking and CRM are real MCP stdio
servers. A signed ticket binds case, action, amount, expiry and dual-control ruling,
so a forged or repurposed tool call is rejected at the server boundary.

Policy Composer uses a model only to map an English sentence to typed edits. A
deterministic allowlist rejects invented or immutable paths, validates the complete
governance schema and simulates the candidate across the 200-case corpus before
Compliance can apply it. The new YAML version and decision are hash-logged.

The interface is a Next.js PWA with Security Print visual language, backed by a
FastAPI boundary, Supabase Auth/RLS/PostgREST and one dedicated SLA worker. Live SSE
makes agent/tool execution observable without making the animation the source of
truth.

The public deployment opens on one live proof path. A visitor can execute an
allow-listed fictional complaint without an email or password; the deployed API,
model, MCP bank tools, Supabase rows, signed journal and audit chain run for that
fresh case. Arbitrary uploads are unavailable and the UI labels synthetic input
separately from live execution. The mutation-free operations rehearsal is secondary.
Production staff have no public sign-up path. An Admin enters a colleague's work email and role in **Operators**, Supabase
sends a single-use invitation, and Postgres RLS enforces that role after password
setup.

The Pro surface now behaves as an operations board on desktop and a focused
single-stage register on mobile. Settings, the mobile menu and Axiom use the same
Security Print system, with no horizontal page overflow at 390 or 1,440 pixels.

## 4. Business value — quantified

The verified production evaluation classified 95.90% of the 195 clean cases,
assigned urgency at 98.97%, caught all 5 prompt injections with zero clean false
positives, and completed with zero run errors. Model latency was 2.616 seconds at
p50 and 4.626 seconds at p95; measured model cost was RM0.001025 per case.

The automation target is under 5 minutes versus 90 minutes today—about a 94%
handling-time reduction. The first rollout covers unauthorised transactions and
billing errors, 57% of stated volume, in shadow mode before progressively enabling
threshold-limited auto-resolution. Deadline risk is forecast before breach. Every
approved financial resolution has a balanced journal and an exportable four-page
FMOS pack, reducing both operating time and regulator-file preparation.

## External hackathon evidence to attach

- Full CodeBuddy conversation-history export.
- At least 3 genuine dated CodeBuddy/WorkBuddy screenshots (target 10+).
- WorkBuddy build/run screenshots plus the CaseZero API call log.
- 380×216 cover: `submission/03-cover/casezero-cover-380x216.png` — ready.
- 6:08 narrated demo: `submission/04-demo/CaseZero-Stakeholder-Demo.mp4` — ready.
- Rubric-ordered PPTX/PDF: `submission/02-deck/` — ready.
- Public dashboard/API URL: <https://casezero-alpha.vercel.app> — ready.

Never fabricate proof: Tencent can verify product-side activity.
