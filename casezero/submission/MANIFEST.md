# CaseZero final artifact manifest

Verified 12 August 2026. SHA-256 values identify the reviewed Demo Day files exactly.

| Artifact | Size | Verification | SHA-256 |
|---|---:|---|---|
| `02-deck/Axiom-Demo-Day-Deck.pptx` | 2,018,053 B | 19 slides at 16:9: 13 timed story slides + 1 previous-close reference + 5 appendix/Q&A slides; 19 speaker-note source blocks; no detected overflow; every slide rendered and inspected | `0b92b7e05fb53522fb352dda9335888ffc099f5760485dc0c3a8dd96b58b6ff6` |
| `02-deck/Axiom-Demo-Day-Deck.pdf` | 1,282,393 B | 19 pages at 16:9; every page rendered with Poppler and inspected against the PPTX | `2bc91bfc8dd2dd24efc4469613dfbc71e2cde4a745ab1d08dd3ff505beab939b` |
| `assets/deck/casezero-live-qr.png` | 5,894 B | 720×720 QR; decodes from the source asset, rendered PowerPoint slide 13 and rendered PDF page 13 to the live `/live` route | `1835f03d69018a8a00ce4a2f338599665fff55a8eec8a8f349576d062ba2e288` |
| `03-cover/casezero-cover-380x216.png` | 115,640 B | exact 380×216 RGBA PNG, visually inspected | `cbe3a0bf61750c6dbba1532a2ddfc1000c8047be49d67cef8f92b915dd46cca9` |
| `04-demo/Axiom-Boardroom-Demo.mp4` | 1,489,866 B | 33.76 seconds, 1440×900, 25fps H.264, silent standalone fallback if the live demo cannot run | `4117293f14422a19a3469703dc50bffc8d1758af355a78dfaeab8dcd2d7ef1cd` |
| `04-demo/Axiom-Boardroom-Demo-poster.png` | 342,341 B | real Boardroom browser frame used as the standalone video poster | `cae58935a6f332c3eaad304b69e65a864458dda6f9baa9bcba008d7dba3722b5` |

All customer, bank and transaction data visible in these files is synthetic.
