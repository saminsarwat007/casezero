# CaseZero stakeholder readiness review

## Verdict

CaseZero is sufficient today for stakeholder onboarding, a public synthetic
rehearsal and a controlled synthetic-data pilot. It is not represented as live bank
production. Real customer use remains correctly blocked on bank-owned integrations,
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
| Measurable | 95.90% category, 98.97% urgency, 5/5 attacks, p50/p95 latency, cost, 465 tests and 11 browser journeys | Ready |

## UX decision

The Security Print interface is distinctive and appropriate for a regulated bank.
The Pro issues were density and mobile navigation, not the visual theme: Pro now has
an operational pulse, a focused mobile stage selector, a real mobile menu and no
horizontal overflow. The first-shift guide and Settings make the system usable by a
new non-technical stakeholder.

The original 60.8-second video was not sufficient. It crossed too many routes without
explaining the decision or outcome. It has been replaced by a 6:08 narrated,
chapter-captioned story that follows one complaint and the rubric.

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
