# CaseZero Design System — Security Print

This file is the UI source of truth derived from `MASTERPLAN.md` §14.4. The local
UI/UX database was consulted on 4 Aug 2026 (variance 8, motion 4, density 8). Its
accessibility, responsive, chart and interaction guidance is retained below; its
generic trust-navy/Bento styling was rejected because it conflicts with the
project-specific Security Print direction.

## Product and job

- **Subject:** a governed Malaysian banking-dispute operating system.
- **Primary user:** a five-person, non-technical complaints operations team.
- **Single job:** show what needs a person, explain why, and make the safe action
  unmistakable.
- **Structural metaphor:** double-entry bookkeeping. `CLAIMED` and `OF RECORD`
  form the two sides of every case; verification makes them balance.
- **Operating agent:** Wajar is a docket, not a chat bubble. It must expose action,
  authority, effect, gates and result before an irreversible operation.

## Tokens

| Role | Hex | Token |
|---|---|---|
| Safety-paper stock | `#E4EAE5` | `--paper` |
| Raised paper | `#F2F5F2` | `--panel` |
| Printing ink | `#131A15` | `--ink` |
| Secondary ink | `#5A665D` | `--ink-2` |
| Security line-work | `#A8BFB0` | `--guilloche` |
| Oxblood endorsement | `#8B2333` | `--endorse` |
| X-ray inversion | `#0B0F0C` | `--negative` |
| Focus ring | `#365F48` | `--focus` |

`--endorse` is reserved for breach, tamper and quarantine. PASS uses ink plus a
line pattern, never green alone. No gradients, glow, glass, drop shadows or pure
black.

## Type

- **Instrument Sans:** headings, labels and prose.
- **Martian Mono:** every amount, count, date, case reference and hash.
- Base prose is 16px/1.5. Utility text never drops below 12px.
- Labels use uppercase only when they behave like printed form labels, with
  enough tracking to remain legible.

## Geometry and spacing

- Maximum radius: `2px`; controls may be square or subtly clipped, never pills.
- Elevation is expressed by rules, alternating paper stocks and inset registration
  lines—not shadows.
- Dense ops spacing scale: 4, 8, 12, 16, 24, 32, 48px.
- Minimum target: 44×44px with at least 8px between adjacent actions.
- Desktop shell is asymmetric: a narrow numbered rail, a flexible work surface,
  and an optional evidence column. Below 768px it becomes a single stack.

## Signature system

1. **Generated guilloche:** SVG epitrochoid linework in file headers and audit
   strips. It is code-generated, low contrast and never behind body copy.
2. **Letterpress stamps:** verification and resolution states register into place
   with a 1–2° physical misalignment.
3. **VOID pantograph:** visible only when chain verification fails.
4. **Working-day strip:** weekends are physical gaps, not coloured cells.
5. **Microtext rule:** `CASEZERO·MYBANK·AUDIT·` repeats at section boundaries.
6. **Wajar action docket:** a fixed, accessible control sheet with a visible close,
   explicit confirmation zone and hash-addressed receipt. Never render anthropomorphic
   typing dots or imply a write happened before the server confirms it.

## Motion

- 150–250ms; mechanical registration and rail movement.
- Primary easing: `cubic-bezier(.22,.8,.2,1)`; stamp easing:
  `cubic-bezier(.2,.9,.25,1)`.
- Animate transform and opacity only. No spring overshoot, scroll fade-ups,
  hovering/floating, scale-on-hover or layout-property animation.
- `prefers-reduced-motion: reduce` removes non-essential transforms.

## Components

- **Buttons:** verb-first labels, visible ink rule, 44px minimum, pressed state is
  a 1px registration shift. Dangerous actions use endorse ink plus text, never
  colour alone.
- **Cards:** panel stock, 1px guilloche-tinted rule, optional inner registration
  rule. No universal card hover; only interactive cards advertise interaction.
- **Inputs:** persistent label, helper text, error adjacent to the field, focus
  ring at least 2px. Placeholder is an example, not the label.
- **Tables:** sticky labelled header, text fallback for all status colour, row
  actions reachable by keyboard. Review shortcuts `A/R/I` do not fire while an
  input is focused.
- **Pipeline lanes:** all lanes remain visible on wide screens. Below 768px a
  two-column stage selector exposes one complete lane at a time; content is never
  squeezed into unreadable columns.
- **Mobile navigation:** a labelled menu expands in normal document flow. Do not
  clip or horizontally scroll primary navigation.
- **Charts:** exact values and legends always visible. Category distribution uses
  a labelled donut; performance targets use compact bullet bars; heatmaps expose
  a numeric/table fallback and never rely on colour alone.

## Accessibility and responsive checks

- Contrast ≥4.5:1 for normal text and ≥3:1 for large text/non-text controls.
- Every icon-only control has an accessible label; decorative SVG is hidden.
- Logical heading order, skip link, landmarks and visible keyboard focus.
- `aria-live` for case transitions and review results.
- Verify at 375, 768, 1024 and 1440px with no horizontal page scroll.
- Initial data comes from Next.js server components where auth permits; client
  components are reserved for SSE, keyboard controls and local interactions.
- Loading states reserve space to avoid layout shift.

## Page map

| Route | Primary composition |
|---|---|
| `/login` | One engraved credential sheet, no marketing split-screen |
| `/simple` | Daily ledger: three counters, needs-attention register, command chips |
| `/pro` | Pipeline rails, inverted Agent Theater, measured analytics |
| `/settings` | Stakeholder Control Register, kill switches and settings chain |
| `/case/[ref]` | CLAIMED ↔ OF RECORD balance, evidence, why, journal, chain |
| `/review` | Keyboard-first evidence register with persistent decision panel |
| `/policy` | Plain-English request → protected diff → corpus simulation → govern |
| `/radar` | Merchant/device network and evidence-backed cluster brief |
| `/audit` | Chain explorer and exact broken-sequence VOID state |
| `/quarantine` | Preserved hostile input, detectors and zero-model-call proof |
| `/track/[token]` | Quiet customer paper, large tracker, FMOS rights, proactive card |

## Forbidden patterns

- Generic Bento marketing cards, hero CTA funnels or soft SaaS shadows.
- Trust-navy/green palettes, purple AI accents, glass, gradients or glow.
- Inter/Roboto/Arial/Geist/Fira; emoji icons; unlabeled colour-only status.
- Decorative motion, spring bounce, fade-up-on-scroll and fixed-height mobile
  hero sections.
- Consumer chat bubbles, autonomous-looking write actions or vague “AI is working”
  states. Wajar is an accountable operating control, not a mascot.
