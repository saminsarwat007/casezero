# CaseZero

## Short blurb - 9 words

**Bank disputes resolved in minutes, governed end to end.**

## Chosen challenge

**AI Agent Track - Case Study 1: AI-Powered Banking Dispute Automation Pipeline**

## Project overview

CaseZero is a governed dispute-resolution operating system for a Malaysian regional
bank and its five-person, non-technical complaints team. It converts an email and PDF
evidence into a classified, verified, financially resolved and customer-communicated
case while preserving the BNM working-day deadline, FMOS disclosure, balanced journal
and a complete audit chain.

The product combines six specialised AI agents with **Axiom by CaseZero**, a natural-
language operating agent. Axiom can summarise, navigate, verify evidence and prepare
authorised actions, but it must show the operator its authority, effect and safety gates
before any write. Models propose; a deterministic compliance kernel decides.

## Real-world scenario insight

The case-study bank serves 1.8 million retail and SME customers. Today a complaint
takes 90 minutes across multiple departments and about 11% of regulatory deadlines are
missed. The problem is not only speed: email and PDF evidence contains PII, seven
dispute categories need different rules, investigators must reconcile core-banking and
CRM evidence, and a customer letter must remain compliant even when a model is wrong.

CaseZero therefore treats prompt output as an untrusted proposal. Prompt injection is
screened before a model call; PII is encrypted and redacted; low confidence and
ambiguous evidence fail safe to a person; only MCP evidence returning `PASS` can reach
financial posting; and every transition is hash chained.

## Comprehensive solution design

1. **Intake and security** - parse RFC822 email, extract text, use native PDF vision for
   scanned evidence, encrypt identifiers and quarantine injection attempts pre-LLM.
2. **Classification** - constrain the model to seven exact category codes; the active
   rule pack assigns urgency, confidence floor and the 5/20-working-day SLA.
3. **Verification** - MCP tools cross-reference core banking and CRM and return only
   `PASS`, `FAIL` or `MANUAL_REVIEW`, with cited evidence.
4. **Resolution** - the deterministic gate mints a scoped, expiring posting ticket only
   for `PASS`; the core system posts a balanced double-entry reversal or credit.
5. **Communication** - the model drafts readable sections; code inserts mandatory BNM
   disclosures and the FMOS six-month referral notice for eligible claims.
6. **Supervision** - Mission Control forecasts deadline risk, shows workload and
   accuracy, and lets authorised staff inspect the event chain and journal.
7. **Natural-language operations** - Axiom maps requests to an allowlisted capability,
   reparses writes on the server and issues a durable execution receipt.

Prompt design is deliberately narrow. The classifier and communicator return typed
proposals; Policy Studio maps English instructions to protected configuration diffs;
deterministic validation, not prompt wording, owns money, deadlines and disclosures.

## Business value

- Stretch path from **90 minutes to under 5 minutes** for fully automated `PASS` cases.
- First rollout covers unauthorised transactions and billing errors: **57% of stated volume**.
- Production-model evaluation: **95.90% category accuracy**, **98.97% urgency accuracy**,
  and **5/5 injection attacks detected with zero clean false positives**.
- Model latency: **2.616s p50 / 4.626s p95** at **RM0.001025 per case** in the measured run.
- Release proof: **466 backend tests**, **14 browser journeys**, balanced journals,
  verified hash chains and **0 npm vulnerabilities**.

The live deployment is ready for stakeholder onboarding, safe rehearsal and a
synthetic-data pilot. Real financial rollout additionally requires the bank's core/CRM
credentials, complaint-mailbox transport, compliance sign-off and production security approval.
