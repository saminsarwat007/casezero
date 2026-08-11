# CaseZero stakeholder readiness review

## Verdict

CaseZero is sufficient today for stakeholder onboarding, a public live execution on
sanitized synthetic input, an operating rehearsal and a controlled synthetic-data
pilot. It is not represented as live bank production. Real customer use remains correctly blocked on bank-owned integrations,
identity, email delivery, compliance approval and an always-on SLA worker.

No additional product feature should be added before the hackathon deadline. The
highest-value remaining work is genuine Tencent proof and stakeholder handoff, not
another dashboard or autonomous capability.

## Case Study 1 hard-test

| Requirement | Evidence | Readiness |
|---|---|---|
| Email + PDF/OCR + security | RFC822/PDF intake, Gemini vision fallback, PII encryption/redaction, deterministic pre-LLM firewall | Ready |
| Category, confidence, urgency and SLA | Seven exact categories, typed model proposal, rule-pack urgency/confidence floor, Malaysian working days | Ready |
| MCP verification | Core/CRM MCP servers return `PASS`, `FAIL` or `MANUAL_REVIEW` with evidence | Ready; synthetic adapters until bank credentials arrive |
| Financial resolution | PASS-only gate, scoped signed ticket, amount/expiry binding and balanced double entry | Ready; synthetic core until bank endpoint arrives |
| Compliant communication | Draft + deterministic lint/repair + FMOS six-month referral disclosure | Ready; approved sender still required |
| Dashboard and natural language | Simple, Pro, mobile stage view, Axiom action docket, Settings and Operators | Ready |
| Secure, auditable and scalable | JWT/RLS, encrypted PII, telemetry, continuous hash chain, exact tamper location, dedicated SLA worker contract | Ready; worker host required for continuous operation |
| Measurable | 95.90% category, 98.97% urgency, 5/5 attacks, p50/p95 latency, cost, 501 tests and 29 browser journeys | Ready |

## UX decision

The Security Print interface remains distinctive and appropriate for a regulated
bank, but the rehearsal-first landing and Simple/Pro choice were too abstract for a
new evaluator. The public journey now has one job: run one complaint and read its
live evidence rail. The operations workspace, Simple/Pro modes and Axiom remain
secondary staff tools. Desktop and 390px mobile checks have no horizontal overflow.

The old cross-route film has been replaced by a 5:55.77 live-first,
chapter-captioned story. The first product click waits for a production execution,
then shows model/tool receipts, balanced posting and the chain before entering the
staff workspace. The final explanatory frames are sourced from the redesigned Axiom
deck; none of the archived decorative imagery remains in the submission film.

## Axiom decision

Axiom is implemented as an agentic action docket, not an unrestricted chatbot. It
can summarise operations, expose SLA risk, navigate, verify a chain, invite staff and
prepare settings changes. It displays authority and side effects before execution,
replans writes on the server, requires eligible roles and confirmation, and issues
an `AXR-` receipt. Direct posting is intentionally absent.

## External blockers for live financial use

1. Core/CRM endpoints, credentials and mapping.
2. Complaint mailbox and approved outbound sender.
3. First Admin work identity and named operator roles.
4. Compliance approval of packs, thresholds and letters.
5. Production domain, privacy/security approval and Axiom name clearance.
6. One always-on SLA worker host.
