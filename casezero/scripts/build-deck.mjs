/** Build the Demo Day deck.
 *
 * Design brief: five minutes, judges who have not seen the product, less text and
 * more evidence. So every slide carries at most one sentence of argument and one
 * piece of proof, and the proof is a real screenshot of the running dashboard —
 * captured by `dashboard/scripts/capture-deck-shots.ts`, never redrawn in
 * PowerPoint. If a number appears here it also appears in the repository.
 *
 * The visual language is the product's own "Security Print": banknote paper,
 * double rules, ink stamps, monospace figures, one red reserved for refusal.
 *
 *   node scripts/build-deck.mjs
 */

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import PptxGenJS from "pptxgenjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SHOTS = path.join(ROOT, "submission/assets/deck");
const DEMO = path.join(ROOT, "submission/04-demo");
const OUT = path.join(ROOT, "submission/02-deck/Axiom-Demo-Day-Deck.pptx");

/* ── The product's palette, copied from dashboard/app/globals.css ──────────── */
const C = {
  paper: "E4EAE5",
  panel: "F2F5F2",
  ink: "131A15",
  ink2: "5A665D",
  guilloche: "A8BFB0",
  endorse: "8B2333",
  negative: "0B0F0C",
  focus: "365F48",
};

/* Instrument Sans and Martian Mono are webfonts, so they are not on a judge's
   laptop. The screenshots already carry the real typography; deck chrome uses
   faces that exist everywhere so nothing reflows on a strange machine. */
const SANS = "Helvetica Neue";
const MONO = "Menlo";

const W = 13.333;
const H = 7.5;
const M = 0.62;

const pptx = new PptxGenJS();
pptx.defineLayout({ name: "AXIOM", width: W, height: H });
pptx.layout = "AXIOM";
pptx.author = "CaseZero";
pptx.company = "CaseZero";
pptx.title = "Axiom by CaseZero — Demo Day";
pptx.subject = "Tencent Cloud x UTM Hackathon, Case Study 1: banking dispute resolution";

/** Banknote paper with the faint 80px vertical ruling the site draws in CSS. */
function sheet(slide, { dark = false } = {}) {
  const bg = dark ? C.negative : C.paper;
  slide.background = { color: bg };
  const step = 0.55;
  for (let x = step; x < W; x += step) {
    slide.addShape(pptx.ShapeType.rect, {
      x, y: 0, w: 0.008, h: H,
      fill: { color: dark ? "FFFFFF" : C.ink, transparency: dark ? 96 : 96 },
      line: { type: "none" },
    });
  }
}

/** The double rule used as every major separator in the product. */
function doubleRule(slide, y, { dark = false, x = M, w = W - M * 2 } = {}) {
  const color = dark ? "FFFFFF" : C.ink;
  const alpha = dark ? 70 : 0;
  slide.addShape(pptx.ShapeType.rect, { x, y, w, h: 0.022, fill: { color, transparency: alpha }, line: { type: "none" } });
  slide.addShape(pptx.ShapeType.rect, { x, y: y + 0.055, w, h: 0.008, fill: { color, transparency: alpha + 20 }, line: { type: "none" } });
}

function eyebrow(slide, text, { y = M, dark = false, x = M, w = W - M * 2 } = {}) {
  slide.addText(text.toUpperCase(), {
    x, y, w, h: 0.26,
    fontFace: MONO, fontSize: 10, bold: true, charSpacing: 2.6,
    color: dark ? C.guilloche : C.ink2,
  });
}

function headline(slide, text, { y = 1.02, size = 46, dark = false, w = W - M * 2, color } = {}) {
  slide.addText(text, {
    x: M, y, w, h: size > 40 ? 1.5 : 1.1,
    fontFace: SANS, fontSize: size, bold: true, charSpacing: -1.4, lineSpacing: size * 1.02,
    color: color ?? (dark ? C.panel : C.ink), valign: "top",
  });
}

function lede(slide, text, { y, w = 7.2, dark = false } = {}) {
  slide.addText(text, {
    x: M, y, w, h: 0.95,
    fontFace: SANS, fontSize: 15.5, lineSpacing: 22,
    color: dark ? C.guilloche : C.ink2, valign: "top",
  });
}

function footer(slide, left, right, { dark = false } = {}) {
  const color = dark ? C.ink2 : C.ink2;
  slide.addText(left.toUpperCase(), {
    x: M, y: H - 0.5, w: 8, h: 0.26, fontFace: MONO, fontSize: 8, charSpacing: 1.8, color,
  });
  if (right) {
    slide.addText(right.toUpperCase(), {
      x: W - M - 4.6, y: H - 0.5, w: 4.6, h: 0.26,
      fontFace: MONO, fontSize: 8, charSpacing: 1.8, color, align: "right",
    });
  }
}

/** A framed screenshot: 1px ink border plus the inset guilloché outline the
 *  product uses on every panel. */
function plate(slide, file, { x, y, w, h }) {
  slide.addShape(pptx.ShapeType.rect, {
    x: x - 0.035, y: y - 0.035, w: w + 0.07, h: h + 0.07,
    fill: { color: C.panel }, line: { color: C.ink, width: 1 },
  });
  slide.addImage({ path: path.join(SHOTS, file), x, y, w, h, sizing: { type: "contain", w, h } });
}

/** One big monospace figure with a plain-English caption underneath. */
function figure(slide, { x, y, w, value, label, dark = false, accent }) {
  slide.addText(value, {
    x, y, w, h: 1.02,
    fontFace: MONO, fontSize: 40, bold: true, charSpacing: -2,
    color: accent ?? (dark ? C.panel : C.ink), valign: "top",
  });
  slide.addText(label, {
    x, y: y + 1.05, w, h: 0.8,
    fontFace: SANS, fontSize: 12.5, lineSpacing: 17,
    color: dark ? C.guilloche : C.ink2, valign: "top",
  });
}

/** A bordered card. Returns nothing; text is added by the caller. */
function card(slide, { x, y, w, h, dark = false, accent = null }) {
  slide.addShape(pptx.ShapeType.rect, {
    x, y, w, h,
    fill: { color: dark ? "141B16" : C.panel },
    line: { color: accent ?? (dark ? "2A342C" : C.ink), width: accent ? 1.5 : 0.75 },
  });
}

/** The kernel's stamp, drawn rather than screenshotted so it can sit inline. */
function stamp(slide, { x, y, w = 2.45, text, gate, refused = false }) {
  const color = refused ? C.endorse : C.ink;
  slide.addShape(pptx.ShapeType.rect, {
    x, y, w, h: 0.95, fill: { color: C.paper }, line: { color, width: 3.25 }, rotate: refused ? 1.4 : -1.5,
  });
  slide.addText(text, {
    x, y: y + 0.12, w, h: 0.42, align: "center",
    fontFace: MONO, fontSize: 17, bold: true, charSpacing: 2, color, rotate: refused ? 1.4 : -1.5,
  });
  slide.addText(gate.toUpperCase(), {
    x, y: y + 0.56, w, h: 0.26, align: "center",
    fontFace: MONO, fontSize: 7.5, charSpacing: 1.6, color, rotate: refused ? 1.4 : -1.5,
  });
}

/* ═══════════════════════ 01 · Title ═══════════════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "Tencent Cloud × UTM Hackathon / Case Study 1 / Demo Day");
  doubleRule(s, 1.05);

  s.addText("Axiom", {
    x: M, y: 1.35, w: 10, h: 1.5,
    fontFace: SANS, fontSize: 96, bold: true, charSpacing: -4, color: C.ink,
  });
  s.addText("by CaseZero", {
    x: M, y: 2.72, w: 10, h: 0.5,
    fontFace: MONO, fontSize: 15, charSpacing: 3.4, color: C.ink2,
  });

  headline(s, "An AI dispute team that can be\nput on the record.", { y: 3.62, size: 38 });

  doubleRule(s, 5.55);
  const cols = [
    ["6 agents", "each with its own brain"],
    ["1 kernel", "deterministic, cannot be argued with"],
    ["4.2 seconds", "against a 90-minute manual baseline"],
  ];
  cols.forEach(([value, label], index) => {
    const x = M + index * ((W - M * 2) / 3);
    s.addText(value, { x, y: 5.78, w: 3.6, h: 0.4, fontFace: MONO, fontSize: 16, bold: true, color: C.ink });
    s.addText(label, { x, y: 6.18, w: 3.7, h: 0.4, fontFace: SANS, fontSize: 11.5, color: C.ink2 });
  });

  footer(s, "Synthetic customers · real pipeline", "casezero-alpha.vercel.app");
}

/* ═══════════════════════ 02 · The problem ═════════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "The problem");
  headline(s, "Ninety minutes a case.\nAnd one deadline in nine is missed.", { y: 1.0, size: 40 });
  lede(s, "A Malaysian regional bank resolves disputes by hand, across departments, under a regulator that counts the days.", { y: 2.72, w: 8.6 });

  doubleRule(s, 3.72);
  const stats = [
    ["1.8M", "retail and SME customers filing complaints"],
    ["90 min", "average handling time, spread over several desks"],
    ["11%", "of BNM regulatory deadlines missed today", C.endorse],
    ["5–20", "working days allowed, by complexity"],
  ];
  stats.forEach(([value, label, accent], index) => {
    figure(s, { x: M + index * 3.1, y: 4.05, w: 2.85, value, label, accent });
  });

  s.addText("Delay is not one queue problem. It is a handoff problem — evidence, authority and ownership drift apart between desks.", {
    x: M, y: 6.22, w: 11.9, h: 0.45, fontFace: SANS, fontSize: 13, bold: true, color: C.ink, align: "center",
  });

  footer(s, "Source: Case Study 1 brief · BNM Complaints Handling · FMOS");
}

/* ═══════════════════════ 03 · Who benefits ════════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "Who benefits");
  headline(s, "Written for the person holding\nthe complaint, not the engineer.", { y: 1.0, size: 38 });
  doubleRule(s, 2.88);

  const people = [
    [
      "The complaints lead",
      "Non-technical. Owns the deadline.",
      "Reads plain English — “checked against bank records”, never VERIFICATION_COMPLETED. Sees which cases need a human and which are already done.",
    ],
    [
      "The customer",
      "Wants their money back.",
      "Answered in minutes instead of weeks, in English or Malay, with the FMOS six-month referral right included by the kernel rather than remembered by a person.",
    ],
    [
      "The regulator and auditor",
      "Wants to know who decided.",
      "Every stage is one hashed, sequenced event. Any line in the interface opens into the receipt behind it, including the refusals.",
    ],
  ];
  people.forEach(([who, role, what], index) => {
    const x = M + index * 4.07;
    card(s, { x, y: 3.18, w: 3.78, h: 3.35 });
    s.addText(who, { x: x + 0.26, y: 3.42, w: 3.26, h: 0.4, fontFace: SANS, fontSize: 16.5, bold: true, color: C.ink });
    s.addText(role.toUpperCase(), { x: x + 0.26, y: 3.84, w: 3.26, h: 0.3, fontFace: MONO, fontSize: 7.5, charSpacing: 1.4, color: C.ink2 });
    s.addText(what, { x: x + 0.26, y: 4.22, w: 3.26, h: 2.1, fontFace: SANS, fontSize: 12, lineSpacing: 16.5, color: C.ink, valign: "top" });
  });

  footer(s, "Human-centred design · plain language over enum names");
}

/* ═══════════════════════ 04 · The solution ════════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "The solution");
  headline(s, "Six agents pass one real case.\nA kernel stamps every handoff.", { y: 0.98, size: 30, w: 6.3 });
  lede(s, "Not a chat window and not a black box. A boardroom you can watch, where the case file only moves once its evidence is written.", { y: 3.0, w: 5.9 });

  s.addText("This is a screenshot of the running product.", {
    x: M, y: 4.05, w: 5.9, h: 0.36, fontFace: MONO, fontSize: 8.5, charSpacing: 1.4, color: C.ink2,
  });
  stamp(s, { x: M, y: 4.55, text: "AUTHORISED", gate: "Financial gate" });
  s.addText("The kernel never has a thinking state. It snaps.", {
    x: M + 2.75, y: 4.72, w: 3.1, h: 0.7, fontFace: SANS, fontSize: 12.5, italic: true, color: C.ink2,
  });

  plate(s, "boardroom-complete.png", { x: 6.95, y: 0.62, w: 5.78, h: 6.26 });
  footer(s, "/live · the boardroom is the default view");
}

/* ═══════════════════════ 05 · How it works ════════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "How it works");
  headline(s, "Seven stages. Every one of them\nleaves a receipt.", { y: 0.98, size: 36 });
  doubleRule(s, 2.78);

  const stages = [
    ["01", "Check for\nharmful content", "Intake", "15", true],
    ["02", "Identify the\ncomplaint type", "Classifier", "12", true],
    ["03", "Set priority\nand deadline", "Kernel", "8", false],
    ["04", "Check against\nbank records", "Verifier · MCP", "25", false],
    ["05", "Auto-resolve or\nhuman review", "Kernel", "10", false],
    ["06", "Move\nthe money", "Resolver", "12", false],
    ["07", "Send response\nto customer", "Communicator", "8", true],
  ];
  const cw = (W - M * 2 - 0.12 * 6) / 7;
  stages.forEach(([n, label, actor, mins, usesModel], index) => {
    const x = M + index * (cw + 0.12);
    const isKernel = actor === "Kernel";
    card(s, { x, y: 3.1, w: cw, h: 2.5, accent: isKernel ? C.ink : null });
    s.addText(n, { x: x + 0.16, y: 3.25, w: cw - 0.3, h: 0.28, fontFace: MONO, fontSize: 9, bold: true, color: isKernel ? C.ink : C.ink2 });
    s.addText(label, { x: x + 0.16, y: 3.58, w: cw - 0.3, h: 0.92, fontFace: SANS, fontSize: 11.5, bold: true, lineSpacing: 14.5, color: C.ink, valign: "top" });
    s.addText(actor.toUpperCase(), { x: x + 0.16, y: 4.62, w: cw - 0.3, h: 0.5, fontFace: MONO, fontSize: 7, charSpacing: 1.1, color: isKernel ? C.ink : C.ink2, valign: "top" });
    s.addText(usesModel ? "MODEL" : "NO MODEL", {
      x: x + 0.16, y: 5.16, w: cw - 0.3, h: 0.28,
      fontFace: MONO, fontSize: 6.5, charSpacing: 0.8, color: usesModel ? C.focus : C.ink2,
    });
    s.addText(`${mins} min manual`, { x: x + 0.16, y: 5.42, w: cw - 0.3, h: 0.24, fontFace: MONO, fontSize: 6.5, color: C.ink2 });
  });

  doubleRule(s, 5.92);
  s.addText("Models propose. The kernel disposes.", {
    x: M, y: 6.12, w: 7.5, h: 0.5, fontFace: SANS, fontSize: 21, bold: true, charSpacing: -0.7, color: C.ink,
  });
  s.addText("15 + 12 + 8 + 25 + 10 + 12 + 8 = 90 manual minutes, decomposed per desk", {
    x: W - M - 5.4, y: 6.24, w: 5.4, h: 0.4, fontFace: MONO, fontSize: 8.5, color: C.ink2, align: "right",
  });

  footer(s, "api/agents/roster.py · one stage list shared by the feed, the proof and the tests");
}

/* ═══════════════════════ 06 · AI, meaningfully ════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "How AI is meaningfully used");
  headline(s, "The two seats closest to the money\nhave no brain to be talked out of.", { y: 0.98, size: 34 });
  lede(s, "Model diversity is easy to fake. We removed the models from the seats where a persuasive sentence could move funds, and we say so in the interface.", { y: 2.74, w: 9.4 });

  doubleRule(s, 3.68);
  const panels = [
    ["Where a model helps", "Gemini · Groq", "Reading a messy email, transcribing a scanned PDF, choosing among seven categories, drafting a letter. Judgement under ambiguity — with a confidence floor.", C.focus],
    ["Where no model runs", "0 calls", "Verifying the claim against core banking over MCP, and posting the journal. These seats compare records and check a signed ticket. They do not reason.", C.ink],
    ["Who actually decides", "The kernel", "Urgency, the BNM working-day deadline, whether money may move, the FMOS wording and every status transition. Rule pack, not prompt.", C.endorse],
  ];
  panels.forEach(([title, tag, body, accent], index) => {
    const x = M + index * 4.07;
    card(s, { x, y: 3.98, w: 3.78, h: 2.62, accent });
    s.addText(tag.toUpperCase(), { x: x + 0.26, y: 4.18, w: 3.26, h: 0.3, fontFace: MONO, fontSize: 8, bold: true, charSpacing: 1.4, color: accent });
    s.addText(title, { x: x + 0.26, y: 4.5, w: 3.26, h: 0.4, fontFace: SANS, fontSize: 15.5, bold: true, color: C.ink });
    s.addText(body, { x: x + 0.26, y: 4.94, w: 3.26, h: 1.5, fontFace: SANS, fontSize: 11.5, lineSpacing: 16, color: C.ink2, valign: "top" });
  });

  footer(s, "Responsible AI · a model never holds authority", "Verifier and Resolver are absent from the model router");
}

/* ═══════════════════════ 07 · The demo film ═══════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s, { dark: true });
  eyebrow(s, "Live demo / 33 seconds", { dark: true });
  s.addText("One complaint you write yourself.\nSeven stages. One refusal.", {
    x: M, y: 1.0, w: 5.5, h: 1.9,
    fontFace: SANS, fontSize: 30, bold: true, charSpacing: -1, lineSpacing: 34, color: C.panel, valign: "top",
  });
  s.addText(
    "Press play, or run it live at casezero-alpha.vercel.app/live. Nothing in this film is a mockup: the network is stubbed from the same fixtures the 29 browser tests assert against, and the page is the deployed one.",
    { x: M, y: 3.15, w: 5.3, h: 1.9, fontFace: SANS, fontSize: 12.5, lineSpacing: 18, color: C.guilloche, valign: "top" },
  );
  s.addText("The moment to watch for", {
    x: M, y: 5.05, w: 5.3, h: 0.3, fontFace: MONO, fontSize: 8, charSpacing: 1.6, color: C.guilloche,
  });
  s.addText("An injected instruction arrives. Six brains stay silent and a red REFUSED stamp lands, with zero model calls made.", {
    x: M, y: 5.38, w: 5.3, h: 1.1, fontFace: SANS, fontSize: 13, bold: true, lineSpacing: 18, color: C.panel, valign: "top",
  });

  // `cover` only accepts a base64 data URI, so the poster is inlined. Without it
  // PowerPoint shows a grey play button instead of the boardroom.
  const poster = await fs.readFile(path.join(DEMO, "Axiom-Boardroom-Demo-poster.png"));
  s.addMedia({
    type: "video",
    path: path.join(DEMO, "Axiom-Boardroom-Demo.mp4"),
    cover: `data:image/png;base64,${poster.toString("base64")}`,
    x: 6.35, y: 1.25, w: 6.38, h: 3.99,
  });
  s.addText("Axiom-Boardroom-Demo.mp4 · 1440×900 · submission/04-demo/", {
    x: 6.35, y: 5.38, w: 6.38, h: 0.3, fontFace: MONO, fontSize: 7.5, charSpacing: 1, color: C.ink2, align: "right",
  });

  footer(s, "If the embed will not play, open submission/04-demo/Axiom-Boardroom-Demo.mp4", null, { dark: true });
}

/* ═══════════════════════ 08 · The receipt ═════════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "Why you can believe the animation");
  headline(s, "Click any line. It opens\ninto its own receipt.", { y: 0.98, size: 34, w: 5.6 });
  lede(s, "Every sentence on the table is assembled in code from an event already on the hash chain. A stage with no event says nothing at all — the seat simply stays quiet.", { y: 2.68, w: 5.5 });

  const facts = [
    ["Sequence number", "Its position in the append-only chain"],
    ["Hash", "The link that makes tampering detectable"],
    ["Event type", "The row the sentence was built from"],
    ["Model calls", "Stated per seat, including “none”"],
  ];
  facts.forEach(([k, v], index) => {
    const y = 4.02 + index * 0.62;
    s.addText(k.toUpperCase(), { x: M, y, w: 1.85, h: 0.3, fontFace: MONO, fontSize: 8, charSpacing: 1.2, color: C.ink2 });
    s.addText(v, { x: M + 1.95, y: y - 0.03, w: 3.6, h: 0.42, fontFace: SANS, fontSize: 12, color: C.ink, valign: "top" });
    s.addShape(pptx.ShapeType.rect, { x: M, y: y + 0.42, w: 5.55, h: 0.006, fill: { color: C.ink, transparency: 82 }, line: { type: "none" } });
  });

  plate(s, "receipt-open.png", { x: 6.6, y: 0.98, w: 6.13, h: 5.5 });
  footer(s, "No bubble may render text that does not derive from a chained event");
}

/* ═══════════════════════ 09 · The refusal ═════════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "Responsible AI / the best moment in the demo");
  headline(s, "An AI being told no.", { y: 0.96, size: 44, color: C.endorse, w: 6.2 });
  lede(s, "A complaint arrives carrying an instruction aimed at the assistant instead of a description of a dispute. The firewall runs before the first model call, so there is nothing to jailbreak.", { y: 2.42, w: 5.8 });

  stamp(s, { x: M, y: 3.85, w: 2.5, text: "REFUSED", gate: "Injection firewall", refused: true });

  const points = [
    "Zero model calls made — the block is upstream of them all.",
    "Every downstream seat reads “Never saw it”, not “skipped”.",
    "No savings are claimed for a refused case. The value of a refusal is the loss that never happened, and we do not put a number on that.",
  ];
  points.forEach((text, index) => {
    const y = 4.86 + index * 0.62;
    s.addShape(pptx.ShapeType.rect, { x: M, y: y + 0.09, w: 0.1, h: 0.1, fill: { color: C.endorse }, line: { type: "none" } });
    s.addText(text, { x: M + 0.26, y: y - 0.05, w: 5.5, h: 0.62, fontFace: SANS, fontSize: 12, lineSpacing: 16, color: C.ink, valign: "top" });
  });

  plate(s, "boardroom-refused.png", { x: 6.6, y: 0.62, w: 6.13, h: 6.26 });
  footer(s, "Foreign identifiers are refused, never silently scrubbed");
}

/* ═══════════════════════ 10 · Business value ══════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "Business value / investigator time freed");
  headline(s, "We show which numbers we measured\nand which we assumed.", { y: 0.96, size: 31, w: 8.6 });
  lede(s, "A bigger number is easy. A number a compliance officer can take apart is worth more, so the three kinds are labelled and never mixed.", { y: 2.5, w: 8.4 });

  plate(s, "value-ledger.png", { x: M, y: 3.36, w: 8.05, h: 3.4 });

  const tiers = [
    ["MEASURED", "Timestamps on this run's chain", C.ink],
    ["BASELINE", "The brief's 90 minutes, split per desk", C.ink2],
    ["ASSUMPTION", "Rate and volume — editable on screen", C.ink2],
  ];
  tiers.forEach(([tag, body, color], index) => {
    const y = 3.42 + index * 0.98;
    s.addShape(pptx.ShapeType.rect, {
      x: 9.05, y, w: 1.5, h: 0.28,
      fill: index === 0 ? { color: C.ink } : { type: "none" },
      line: { color, width: 1, dashType: index === 0 ? "solid" : index === 1 ? "dash" : "sysDot" },
    });
    s.addText(tag, { x: 9.05, y: y + 0.02, w: 1.5, h: 0.24, align: "center", fontFace: MONO, fontSize: 7.5, bold: true, charSpacing: 0.8, color: index === 0 ? C.panel : color });
    s.addText(body, { x: 9.05, y: y + 0.34, w: 3.68, h: 0.6, fontFace: SANS, fontSize: 11.5, lineSpacing: 15, color: C.ink2, valign: "top" });
  });

  card(s, { x: 9.05, y: 6.36, w: 3.68, h: 0.4 });
  s.addText("89.9 analyst minutes handed back, this case", {
    x: 9.05, y: 6.4, w: 3.68, h: 0.32, align: "center", fontFace: MONO, fontSize: 9, bold: true, color: C.ink,
  });

  footer(s, "“Investigator time freed” is a metric the brief asks for by name");
}

/* ═══════════════════════ 11 · Measured ════════════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s, { dark: true });
  eyebrow(s, "Technical execution / measured, not asserted", { dark: true });
  headline(s, "Everything above is checked in.", { y: 1.0, size: 38, dark: true });
  doubleRule(s, 2.34, { dark: true });

  const row1 = [
    ["95.90%", "category accuracy across 195 clean cases"],
    ["98.97%", "urgency accuracy on the same run"],
    ["5 / 5", "injection attacks blocked, zero false positives"],
  ];
  const row2 = [
    ["504", "backend tests passing"],
    ["29", "browser journeys, 12 on the boardroom alone"],
    ["0", "npm vulnerabilities at high or above"],
  ];
  row1.forEach(([v, l], i) => figure(s, { x: M + i * 4.07, y: 2.72, w: 3.7, value: v, label: l, dark: true }));
  doubleRule(s, 4.5, { dark: true });
  row2.forEach(([v, l], i) => figure(s, { x: M + i * 4.07, y: 4.86, w: 3.7, value: v, label: l, dark: true }));

  footer(s, "RM0.001025 per case · 2.616s p50 / 4.626s p95 model latency", "Continuous hash chain · 13 valid links per case", { dark: true });
}

/* ═══════════════════════ 12 · UX and accessibility ════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "User experience and accessibility");
  headline(s, "The scariest states get\nthe best typography.", { y: 0.98, size: 34, w: 6.4 });
  lede(s, "Refused, degraded and held-for-human are designed states, not red toasts. Every path carries the whole story.", { y: 2.62, w: 6.2 });

  const items = [
    ["390px", "The oval becomes a vertical relay. No horizontal overflow, asserted in a test."],
    ["Reduced motion", "Falls back to the checklist rail — the animation goes, the evidence stays."],
    ["Screen reader", "A live region announces each handoff as “Verifier to Kernel: …”."],
    ["Keyboard", "Every receipt is a real button. Skip link, visible focus ring, AA contrast."],
    ["Degraded", "If a model key is missing, the seat says so instead of claiming diversity."],
  ];
  items.forEach(([k, v], index) => {
    const y = 3.62 + index * 0.66;
    s.addText(k.toUpperCase(), { x: M, y, w: 1.75, h: 0.3, fontFace: MONO, fontSize: 8, bold: true, charSpacing: 1.2, color: C.ink });
    s.addText(v, { x: M + 1.85, y: y - 0.04, w: 4.5, h: 0.6, fontFace: SANS, fontSize: 11.5, lineSpacing: 15, color: C.ink2, valign: "top" });
    s.addShape(pptx.ShapeType.rect, { x: M, y: y + 0.46, w: 6.35, h: 0.006, fill: { color: C.ink, transparency: 84 }, line: { type: "none" } });
  });

  plate(s, "boardroom-mobile-fold.png", { x: 9.15, y: 0.7, w: 2.82, h: 6.1 });

  footer(s, "prefers-reduced-motion and the screen-reader path carry the full story");
}

/* ═══════════════════════ 13 · Feasibility ═════════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "Feasibility / what is real today");
  headline(s, "Deployed and running. What is\nleft is the bank's to hand over.", { y: 0.98, size: 34 });
  doubleRule(s, 2.82);

  card(s, { x: M, y: 3.12, w: 5.9, h: 3.4, accent: C.focus });
  s.addText("REAL NOW", { x: M + 0.28, y: 3.34, w: 5.3, h: 0.3, fontFace: MONO, fontSize: 8.5, bold: true, charSpacing: 1.6, color: C.focus });
  s.addText(
    "FastAPI on Vercel · Gemini and Groq routing · MCP core-banking and CRM servers over stdio · Supabase with row-level security · encrypted PII · append-only hashed events · balanced double-entry journals · scheduled SLA worker · public runner with rate limits",
    { x: M + 0.28, y: 3.72, w: 5.3, h: 2.5, fontFace: SANS, fontSize: 12.5, lineSpacing: 18, color: C.ink, valign: "top" },
  );

  card(s, { x: M + 6.2, y: 3.12, w: 5.9, h: 3.4 });
  s.addText("THE BANK SUPPLIES", { x: M + 6.48, y: 3.34, w: 5.3, h: 0.3, fontFace: MONO, fontSize: 8.5, bold: true, charSpacing: 1.6, color: C.ink2 });
  s.addText(
    "Core banking and CRM credentials in place of the synthetic adapters · the approved complaints mailbox · an approved sending identity · Compliance sign-off on the rule pack · the first Admin identity · a host for the continuous SLA worker",
    { x: M + 6.48, y: 3.72, w: 5.3, h: 2.5, fontFace: SANS, fontSize: 12.5, lineSpacing: 18, color: C.ink2, valign: "top" },
  );

  s.addText("First rollout: unauthorised transactions and billing errors — 57% of stated volume — in shadow mode.", {
    x: M, y: 6.66, w: 12.1, h: 0.4, fontFace: MONO, fontSize: 9, charSpacing: 0.8, color: C.ink2,
  });
  footer(s, "No real customer data has ever entered this system");
}

/* ═══════════════════════ 14 · Close ═══════════════════════════════════════ */
{
  const s = pptx.addSlide();
  sheet(s);
  eyebrow(s, "Try it before you score it");
  headline(s, "Write your own complaint\nand watch it become proof.", { y: 1.15, size: 44 });
  doubleRule(s, 3.5);

  const links = [
    ["Live", "casezero-alpha.vercel.app/live"],
    ["Code", "github.com/saminsarwat007/casezero"],
    ["Film", "submission/04-demo/Axiom-Boardroom-Demo.mp4"],
  ];
  links.forEach(([k, v], index) => {
    const y = 3.78 + index * 0.72;
    s.addText(k.toUpperCase(), { x: M, y, w: 1.1, h: 0.34, fontFace: MONO, fontSize: 9, bold: true, charSpacing: 1.4, color: C.ink2 });
    s.addText(v, { x: M + 1.2, y: y - 0.06, w: 8.4, h: 0.44, fontFace: MONO, fontSize: 15, color: C.ink, valign: "top" });
  });

  plate(s, "landing.png", { x: 8.6, y: 3.62, w: 4.13, h: 2.75 });

  s.addText("Models propose. The kernel disposes.", {
    x: M, y: 6.32, w: 7.6, h: 0.5, fontFace: SANS, fontSize: 19, bold: true, charSpacing: -0.6, color: C.ink,
  });
  footer(s, "Axiom by CaseZero · Case Study 1 · synthetic customers, real pipeline");
}

const missing = [];
for (const file of ["landing.png", "boardroom-complete.png", "boardroom-refused.png", "receipt-open.png", "value-ledger.png", "boardroom-mobile-fold.png"]) {
  try {
    await fs.access(path.join(SHOTS, file));
  } catch {
    missing.push(file);
  }
}
if (missing.length) {
  throw new Error(
    `Missing screenshots: ${missing.join(", ")}. Run: npx tsx dashboard/scripts/capture-deck-shots.ts`,
  );
}

await fs.mkdir(path.dirname(OUT), { recursive: true });
await pptx.writeFile({ fileName: OUT });
console.log(`Wrote ${OUT}`);
