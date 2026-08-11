# Axiom by CaseZero — Demo Day run of show

This is a five-minute, deck-led story with a **33.76-second silent product film** embedded on slide 7. The presenter narrates the film live, then can open the deployed `/live` route for a visitor-written complaint if venue connectivity is stable. The older `CaseZero-Stakeholder-Demo.mp4` is retained only as an archive; it predates the composer and Boardroom and is not the Demo Day film.

| Time | Slide / visual | Presenter job | Demo Day criteria |
|---|---|---|---|
| 0:00–0:25 | 1 — Axiom | “An AI dispute team that can be put on the record.” Name Case Study 1 and the evidence/authority boundary. | Impact & Relevance; Demo & Storytelling |
| 0:25–0:55 | 2 — 90 minutes / 11% | Connect delay to evidence, authority and ownership drifting between desks. | Impact & Relevance |
| 0:55–1:15 | 3 — who benefits | Complaints lead, customer, regulator/auditor; plain English over internal enums. | Human-Centered Design |
| 1:15–1:40 | 4–6 — solution and seven seats | “Models propose. The kernel disposes.” Explain why Verifier, Resolver and the financial gate have no model. | AI Interaction; Innovation & Creativity |
| 1:40–2:20 | 7 — embedded Boardroom film | Start the film. Narrate intake → classifier → verifier → kernel → resolver → communicator. Point out the receipt opening and the refusal ending. | Demo & Storytelling; Technical Execution |
| 2:20–2:45 | 8 — every line has a receipt | Click a line if live. Show sequence, hash, event type and model-call count. | Technical Execution; Overall Quality |
| 2:45–3:15 | 9 — refusal | “The most important action is the one that never happened.” Injection is blocked before any model call; downstream seats say “Never saw it”; no savings are claimed. | Responsible AI & Ethics |
| 3:15–3:45 | 10 — value ledger | Separate measured timestamps, the 90-minute baseline and editable rate/volume assumptions. | Impact & Relevance; Feasibility |
| 3:45–4:10 | 11 — checked evidence | 95.90% category accuracy, 98.97% urgency accuracy, 5/5 attacks, 501 backend tests, 29 browser journeys and 0 high-or-above npm vulnerabilities. | Overall Quality; Technical Execution |
| 4:10–4:35 | 12 — UX/accessibility | 390px relay, keyboard receipts, screen-reader handoffs, reduced motion and honest degraded states. | UX & Accessibility; Human-Centered Design |
| 4:35–4:50 | 13 — real now / bank supplies | Distinguish the deployed synthetic pipeline from bank-owned production inputs and sign-off. | Feasibility |
| 4:50–5:00 | 14 — close | Invite the judge to write a complaint at `/live`: “Models propose. The kernel disposes.” | Demo & Storytelling |

## Narration guardrails

- Say “production-grade prototype with synthetic bank data,” not “live bank production.”
- Never claim a model approves money. Say “the model proposes; the signed kernel gate authorises.”
- Pause at each before/after transition. The viewer should understand the outcome before the next click.
- Keep the cursor visible, highlight each click and leave important evidence on screen for at least three seconds.
- Do not call the short embedded film a mockup: it is a real browser capture of the shipped component tree with deterministic network fixtures.
- Do not claim the stubbed film is proof of production connectivity. Use the deployed end-to-end check for that claim.

## Final artifacts

- `Axiom-Boardroom-Demo.mp4` — 1440×900 H.264, 25fps, 33.76 seconds, silent presenter film embedded in slide 7.
- `Axiom-Boardroom-Demo-poster.png` — fallback/poster frame for the embedded film.
- `Axiom-Demo-Day-Deck.pptx` — 14-slide editable deck with embedded film.
- `Axiom-Demo-Day-Deck.pdf` — visually verified font-independent fallback; the PDF shows the film poster.
