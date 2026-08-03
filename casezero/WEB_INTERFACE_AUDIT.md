# CaseZero Web Interface Audit

Reviewed 4 Aug 2026 against the current Vercel Web Interface Guidelines. Findings
below record the pre-remediation locations; all are resolved in the release tree.

## `dashboard/app/review/page.tsx`

- `review/page.tsx:53` — clickable table row was not a semantic action; selection is now a labelled button.
- `review/page.tsx:58` — rejection had no destructive-action confirmation; it now requires confirmation.
- `review/page.tsx:58` — textarea lacked `name` and autocomplete intent; both are explicit.

## `dashboard/app/login/page.tsx`

- `login/page.tsx:46` — auth inputs lacked names and email spellcheck control; fixed.

## `dashboard/app/policy/page.tsx`

- `policy/page.tsx:99` — policy controls lacked names and autocomplete intent; fixed.
- `policy/page.tsx:107` — risk feedback was not announced; it is now an alert.

## `dashboard/app/simple/page.tsx`

- `simple/page.tsx:43` — programmatic file picker lacked an accessible name; fixed.
- `simple/page.tsx:64` — loading skeletons were silent; they now expose polite status text.

## `dashboard/app/radar/page.tsx`

- `radar/page.tsx:30` — “Open evidence register” was a button with no action; it is now a real link.

## `dashboard/components/app-shell.tsx`

- `app-shell.tsx:35` — active navigation lacked `aria-current`; fixed.

## `dashboard/app/globals.css`

- `globals.css:16` — touch actions, balanced headings and heading anchor offsets were absent; fixed.
- `globals.css:136` — long registers had no rendering containment; `content-visibility` now bounds work.
- `globals.css:226` — customer full-bleed layout ignored device safe areas; fixed.

## Result

No blocking accessibility, semantic-action, destructive-action, focus, motion, or
responsive-layout finding remains. Browser acceptance and responsive visual smoke
are rerun as release gates.

## Stakeholder release addendum

- Pro no longer compresses all pipeline lanes on a narrow viewport. At 390px a
  labelled selector renders one complete lane; at 1,440px all lanes remain visible.
- The app shell now exposes a real mobile menu instead of clipping primary routes.
- Axiom uses an accessible dialog with a close control, Escape handling, labelled
  input, explicit write confirmation and a visible execution receipt.
- Settings fields have persistent labels and make the automatic-resolution effect
  explicit. Save confirmation includes the new settings-chain receipt.
- Screenshots of home, Pro, Settings, Axiom and the expanded mobile menu all measured
  `scrollWidth == clientWidth`. The 11-journey Playwright release suite passed.
