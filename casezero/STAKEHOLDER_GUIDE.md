# CaseZero stakeholder guide

## Start in two minutes

1. Open <https://casezero-alpha.vercel.app>.
2. Choose **Run a Live Complaint**. The fictional customer protects privacy; the
   API, model, MCP bank tools, Supabase case, journal and chain are executed live.
3. Confirm the fresh case reference reaches `COMMUNICATED`, verification is `PASS`,
   the journal is balanced and every stage carries a sequence/hash receipt.
4. Choose **Explore the Operations Workspace** for the mutation-free synthetic
   interface rehearsal, then start in **Today / Simple**.
5. Open **Mission Control** for deadlines, workload, agent health and evaluation;
   open **Axiom** for governed natural-language actions.

The public runner never accepts arbitrary uploads or real customer data. If a live
provider fails, it shows a failure and offers the latest persisted run; it never
substitutes a rehearsal result.

For a known-good reference before running another case, open the final verified
production proof for `MYB-2026-000031`: <https://casezero-alpha.vercel.app/live?run=CA1NdXDduzdYnVZXvzeBSHjTIQD4uIrcWz18oFvrMQI>.

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
