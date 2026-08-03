# CaseZero stakeholder guide

## Start in two minutes

1. Open <https://casezero-alpha.vercel.app>.
2. Choose **Explore the operating workspace** for the mutation-free synthetic rehearsal.
3. Start in **Today / Simple**. The queue contains only cases that need a person.
4. Open **Mission Control** when you need deadlines, workload, agent health or evaluation evidence.
5. Open **Axiom** from any staff screen. Read the capability, authority, side effect and gates before continuing.

## How staff emails are added

There is no public sign-up. During deployment, one bank work email is provisioned as
the first Admin. That Admin opens **Operators**, enters a colleague's full name and
work email, assigns `OPS`, `INVESTIGATOR`, `COMPLIANCE` or `ADMIN`, then sends the
single-use Supabase invitation. Postgres row-level security enforces the role after
password setup. Rehearsal mode demonstrates this flow without sending email.

## Daily operating flow

- **Today / Simple:** act on exceptions and recent cases.
- **Review queue:** approve, reject or request information with assembled evidence.
- **Mission Control:** see case stages, deadline pressure and automation health.
- **Policy Studio:** simulate a plain-English rule change before Compliance applies it.
- **Fraud Radar:** inspect masked transaction clusters.
- **Audit Explorer:** recompute the event chain and locate a tampered link.
- **Quarantine:** inspect attacks stopped before any model call.
- **Settings:** change bank identity, complaint contact, timezone, SLA warning,
  default workspace, Axiom availability and automatic-resolution permission.

## What Axiom can and cannot do

Axiom can summarise operations, show SLA risk, open named work areas, verify a case
chain, invite an operator and prepare governed settings changes. It reparses writes
on the server, checks the caller's role, requires confirmation and issues an `AXR-`
receipt. It has no direct posting capability. A financial adjustment still requires
MCP evidence returning `PASS`, a scoped signed kernel ticket and a balanced journal.

## Safe rollout order

1. Public or internal synthetic rehearsal.
2. Shadow-mode pilot with real integrations but no automatic posting.
3. Compliance review of evidence, letters and thresholds.
4. Thresholded automation for approved categories.
5. Expand only from measured outcomes; use Settings as the visible kill switch.
