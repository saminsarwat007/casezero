# CaseZero final artifact manifest

Verified 12 August 2026. SHA-256 values identify the reviewed Demo Day files exactly.

| Artifact | Size | Verification | SHA-256 |
|---|---:|---|---|
| `02-deck/Axiom-Demo-Day-Deck.pptx` | 2,018,053 B | 19 slides at 16:9: 13 timed story slides + 1 previous-close reference + 5 appendix/Q&A slides; 19 speaker-note source blocks; no detected overflow; every slide rendered and inspected | `0b92b7e05fb53522fb352dda9335888ffc099f5760485dc0c3a8dd96b58b6ff6` |
| `02-deck/Axiom-Demo-Day-Deck.pdf` | 1,282,393 B | 19 pages at 16:9; every page rendered with Poppler and inspected against the PPTX | `2bc91bfc8dd2dd24efc4469613dfbc71e2cde4a745ab1d08dd3ff505beab939b` |
| `assets/deck/casezero-live-qr.png` | 5,894 B | 720×720 QR; decodes from the source asset, rendered PowerPoint slide 13 and rendered PDF page 13 to the live `/live` route | `1835f03d69018a8a00ce4a2f338599665fff55a8eec8a8f349576d062ba2e288` |
| `03-cover/casezero-cover-380x216.png` | 115,640 B | exact 380×216 RGBA PNG, visually inspected | `cbe3a0bf61750c6dbba1532a2ddfc1000c8047be49d67cef8f92b915dd46cca9` |
| `04-demo/CaseZero-Stakeholder-Film.mp4` | 12,752,526 B | 87.00 seconds; 1920×1080, 30fps H.264; 48kHz stereo AAC at -16.0 LUFS / -1.5dBTP; full stream decoded without error; real product footage; verified production metrics; encoded end-frame QR decodes to the live `/live` route | `0f23eeb8bf83741484639ea34075733bd4868103d96e4cddaca524e921043092` |
| `04-demo/CaseZero-Stakeholder-Film-poster.png` | 520,622 B | 1920×1080 real Boardroom frame with the Classifier role and boundary visible; visually inspected | `502c623e5e5fa7652a0c29ba0bbae2296489e035671a45e6935d296cf0880aa5` |
| `04-demo/CaseZero-Stakeholder-Film-contact-sheet.png` | 449,073 B | twelve evenly sampled 480×270 frames covering every story beat; visually inspected for hierarchy, crops and transitions | `3969b8275385f8e76ca5b350267e2c75c1da61bcead04143583d0f4f4998accd` |
| `04-demo/CaseZero-Stakeholder-Film.en.vtt` | 1,505 B | nine timed English caption cues aligned to the nine-scene story | `f60bdd506558d03e4d46aaf980ca9c3e6f387ac6515b53580642b6dfa2852965` |
| `04-demo/CaseZero-Stakeholder-Film-script.md` | 2,184 B | exact voiceover, scene timings, audience, promise and claims shown | `ea219e93c2742810a07f91dd748e3b5d92dec6a99c455d73547746c8bbb9fcd8` |
| `04-demo/Axiom-Boardroom-Demo.mp4` | 1,489,866 B | 33.76 seconds, 1440×900, 25fps H.264, silent standalone fallback if the live demo cannot run | `4117293f14422a19a3469703dc50bffc8d1758af355a78dfaeab8dcd2d7ef1cd` |
| `04-demo/Axiom-Boardroom-Demo-poster.png` | 342,341 B | real Boardroom browser frame used as the standalone video poster | `cae58935a6f332c3eaad304b69e65a864458dda6f9baa9bcba008d7dba3722b5` |

All customer, bank and transaction data visible in these files is synthetic.
