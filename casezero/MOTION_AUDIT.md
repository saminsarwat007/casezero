# CaseZero Motion Audit

Reviewed 4 Aug 2026 against the Kowalski-derived motion standards. This records the
pre-remediation findings and the release decision after the fixes below landed.

## Findings

| Before | After | Why |
| --- | --- | --- |
| `.case-card:hover { transform: translateY(-1px) }` | Border-colour response only | A dense operations card is visited tens of times per day; movement adds friction without explaining state. |
| Skeleton animates `background-position` | Solid moving band uses `transform: translateX()` | Background-position repaints; transform stays on the compositor. |
| Hover rules fire on every pointer type | Hover styling is inside `@media (hover: hover) and (pointer: fine)` | Touch browsers can leave false hover states after a tap. |
| Global reduced-motion rule makes every transition `0.01ms` | Position/ambient movement is removed while useful colour/opacity feedback remains | Reduced motion means gentler motion, not an interface with all feedback erased. |
| Framer Motion `scale` and `rotate` shorthands on the stamp | One full `transform` string, with `useReducedMotion()` suppressing movement | Full transforms are compositor-friendly and the rare endorsement still gets a crisp 220ms ease-out entrance. |
| Ambient progress uses the general UI curve | `linear` constant-motion timing | A looping progress register should not accelerate and decelerate like an entering control. |

## Verdict

**Performance.** The skeleton repaint and Framer Motion shorthands were the only
avoidable compositor risks; both are removed.

**Accessibility.** Pointer-gated hover states and component-specific reduced-motion
behaviour now preserve feedback without movement.

**Approve.** No feel-breaking regression remains, high-frequency review actions do
not animate, interaction durations stay under 300ms, and ambient movement is both
purposeful and suppressible.

## Wajar release addendum

Wajar opens as a short mechanical registration of the docket, never as chat typing
theatre. The visible demo cursor and click ripple exist only in the recording script,
not the product. Reduced-motion removes the docket transform while retaining state
and confirmation feedback. Mobile navigation and stage changes are immediate, so an
operator never waits for decorative motion before acting on an SLA.
