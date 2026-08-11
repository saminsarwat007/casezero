# Axiom UI/UX remediation audit

Verified 12 August 2026 against the current dashboard, the Vercel Web Interface Guidelines, keyboard/mobile/reduced-motion Playwright journeys, and real 1440px/390px browser captures. Screenshots use the shipped component tree with deterministic network fixtures; they are not redrawn mockups.

## Final visual evidence

- Desktop landing: `submission/assets/deck/landing.png`
- Completed Boardroom: `submission/assets/deck/boardroom-complete.png`
- 390px Boardroom fold: `submission/assets/deck/boardroom-mobile-fold.png`
- Refused Boardroom: `submission/assets/deck/boardroom-refused.png`
- Measured/baseline/assumption ledger: `submission/assets/deck/value-ledger.png`

## Issues found and resolved

| # | Surface | Problem | Remediation | Verification |
|---:|---|---|---|---|
| 1 | Landing | Three guide rows reused `/live` as their React key, producing the visible Next.js “1 Issue” badge and unstable reconciliation. | Guide keys now use the stable row index because the same route intentionally appears more than once. | Clean landing capture; no console error in the capture run. |
| 2 | Landing guide | Rows looked clickable but were inert containers. | Each row is a real `Link` with a destination, 44px+ target and directional arrow affordance. | Link semantics exposed to Playwright/accessibility tree. |
| 3 | Landing capture | Next’s development toolbar was baked into prior evidence images. | Capture-only cleanup removes `nextjs-portal` after the page settles; product code is unchanged. | Clean regenerated deck screenshots. |
| 4 | Live composer | Submit stayed silently disabled until hidden character thresholds were met, so users could not discover the requirement or trigger browser validation. | Submit remains enabled when the runner is ready; `required` and `minLength` expose native validation and move focus to the invalid field. | Composer journey passes; type/build clean. |
| 5 | Live attachment | Oversized-file feedback rendered below the whole form, far from the file control. | Added inline `field-error`, `aria-invalid`, `aria-describedby`, and focus return to the file input. | Error is adjacent and announced. |
| 6 | Forms | Live, value, settings, invite, password and Axiom controls lacked consistent `name`, input type or autocomplete metadata. | Added stable names, appropriate types, required/min/max constraints and autocomplete tokens. | Static form sweep shows named controls; browser suite passes. |
| 7 | Composer tabs | Compose/sample controls looked like tabs but lacked the ARIA tab contract and keyboard movement. | Added tab IDs, `aria-controls`, selected state, roving `tabIndex`, Arrow Left/Right, Home and End behavior. | Keyboard behavior covered by the live UI and type checks. |
| 8 | Pro mobile stages | Pipeline stage tabs had the same semantic/keyboard gap. | Added the full tab contract, refs, roving focus and arrow/Home/End navigation. | Mobile Pro browser journey passes. |
| 9 | Value projection | Recomputed annual values used `aria-live="off"`, so assistive technology missed changes. | Each projection result is now polite and atomic. | Editable-assumption journey passes. |
| 10 | Value table | The per-stage ledger had no caption, no mobile scroll hint and no keyboard-scrollable region. | Added a screen-reader caption, visible small-screen hint, labelled region and `tabIndex=0`. | 390px capture remains legible; no horizontal page overflow. |
| 11 | Refused value state | Refusal seats were reduced to 45% opacity, making “Never saw it” hard to read. | Raised intentional muted opacity to 64% while keeping the quiet downstream state visually distinct. | Refusal screenshot inspected at full size. |
| 12 | Axiom drawer | Focus could escape behind the open drawer and was not restored to the launcher. | Added initial focus, Tab/Shift+Tab containment, Escape close and launcher focus restoration. | Axiom rehearsal journey passes. |
| 13 | Axiom drawer | Background page could scroll under the drawer; nested overscroll escaped the panel. | Lock body overflow while open and contain overscroll on scrim/drawer/thread. | Drawer remains spatially stable on desktop/mobile. |
| 14 | Axiom input | Input removed its outline without a replacement. | Added a visible `:focus-within` ring around the complete command row. | Keyboard focus is visible. |
| 15 | Axiom drawer | Close and suggested-prompt targets were below the 44px touch baseline. | Close is 44×44; prompt chips are at least 44px high. | Static target-size review and mobile capture. |
| 16 | Axiom/Policy validation | Axiom and Policy Studio also hid short-input requirements behind disabled buttons. | Added native `required`/`minLength`; buttons disable only during an active request. | Policy Studio and Axiom browser journeys pass. |
| 17 | Global actions | Several non-submit buttons relied on the browser’s implicit button type. | Added explicit `type="button"` across review, audit, simple mode, proactive response, case export and policy governance actions. | Static button sweep leaves no genuine untyped button. |
| 18 | Tables | Review and journal tables lacked a programmatic caption; journal headers lacked column scope. | Added screen-reader captions and `scope="col"` to every journal header. | Accessibility tree carries table purpose and column relationships. |
| 19 | Audit control | The tamper simulation was visually a toggle but did not expose its state. | Added `aria-pressed` and explicit button type. | State now has a programmatic on/off value. |
| 20 | Error messaging | Case-load/export errors were visual only. | Added `role="alert"` to the case error region; kept status vs alert semantics distinct elsewhere. | Error becomes immediately announced. |
| 21 | Touch targets | Brand links, Boardroom view toggle and receipt/table links were under the 44px baseline. | Raised the interactive boxes to at least 44px without enlarging visible typography. | Desktop/mobile captures preserve density. |
| 22 | Mobile devices | Landing/live mastheads and the Axiom drawer ignored display cutouts/home indicators. | Added top and bottom safe-area inset padding. | Layout remains unchanged on ordinary screens and safe on notched devices. |
| 23 | Motion | Hover affordance was missing on guide links and motion overrides were incomplete. | Added a restrained arrow translation and retained a comprehensive `prefers-reduced-motion` fallback. | Reduced-motion browser journey passes with the full evidence story. |
| 24 | Visual hierarchy | Boardroom mobile evidence was a very tall, unreadable full-page crop in the deck. | Added a camera-only fold crop preserving the real 390px layout and used it at readable presentation scale. | Deck slide 12 inspected in PPTX and PDF. |

## Release evidence

- Backend: 501 tests passed.
- Frontend types: `tsc --noEmit` passed.
- Production build: Next.js build passed for all 18 routes shown in the route table.
- Browser: 29 Chromium journeys passed, including mobile, reduced motion, refusal, keyboard review and Axiom governance.
- Dependencies: 0 vulnerabilities reported by `npm audit --audit-level=high`.
- Presentation: 14 slides, no detected overflow, every slide rendered and inspected.
- PDF: 14 pages, every page rendered with Poppler and inspected.
