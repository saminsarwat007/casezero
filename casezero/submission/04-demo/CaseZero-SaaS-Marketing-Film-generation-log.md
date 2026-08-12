# CaseZero SaaS marketing film — generation log

Provenance record for `CaseZero-SaaS-Marketing-Film.mp4` (55.0s, 1920×1080, 30fps
H.264, 48kHz stereo AAC, 12,204,760 B). Produced 12 August 2026 from the
HyperFrames project `video/casezero-marketing/`.

## What is generated, and by what

| Layer | Source | Tool / provenance |
|---|---|---|
| Every visual frame | Real Case Zero UI captures + the real Boardroom product film | Authored as HyperFrames HTML compositions; rendered locally with `hyperframes@0.7.107` |
| Narration (5 lines) | `SCRIPT.md`, locked wording | HeyGen text-to-speech only — voice "Hope" (`05f19352e8f74b0392a8f411eba40de1`), session `a5d1bb5afc734150a8a149a5a594b1f7` → `assets/voice/01.wav`–`05.wav` |
| Music bed | Query: "restrained premium editorial pulse, warm analogue texture, calm forward momentum, no corporate uplift" | HeyGen music retrieval → `assets/bgm/track.mp3`, looped to length, mixed at 0.12 |
| Captions | Word timings from the generated narration | Word-timed caption composition rendered by HyperFrames |

## Real product assets shown (no fabricated UI)

- `assets/composer.png` — live complaint composer (synthetic persona data only)
- `assets/Axiom-Boardroom-Demo.mp4` — real Boardroom product film, trimmed to start at source 8.5s
- `assets/human-review.png` — human-review decision screen
- `assets/mission-control.png` — oversight dashboard
- `assets/landing.png` — live landing page (used only as a blurred, dimmed backdrop)
- `assets/casezero-live-qr.png` — QR to `casezero-alpha.vercel.app/live`

## Rejected generations — not present in this film

- The HeyGen Video Agent's generated **visuals** (session `a5d1bb5afc734150a8a149a5a594b1f7`): watermarked; replaced by HyperFrames-rendered frames.
- The HeyGen Video Agent's **first narration take**: mispronounced the brand; regenerated so "Case Zero" is spoken as two words.
- An earlier presenter/avatar cut: rejected on direction — the film must contain zero humans, avatars, or stock footage.

## Verification before delivery

- `npm run check` (hyperframes@0.7.107): 0 lint/runtime/layout/motion errors; 31/31 text checks pass WCAG AA.
- 23-timestamp snapshot review including both sides of all four hard cuts (9.639 / 17.868 / 28.212 / 39.81s): cuts land clean, no human imagery in any frame.
- Encoded-output QA: 12-frame contact sheet (`CaseZero-SaaS-Marketing-Film-contact-sheet.png`) sampled from the delivered MP4; end-frame QR inspected at full resolution — modules crisp and scannable, URL legible.
