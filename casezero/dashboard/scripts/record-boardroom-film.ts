/** Record the ~50s Boardroom film used on the Demo Day slide.
 *
 * This is the current product, unlike `CaseZero-Stakeholder-Demo.mp4`, which was
 * cut before the composer and the Boardroom existed. It is deliberately silent
 * and short: it runs inside a slide behind a presenter who is talking.
 *
 * As with the deck screenshots, the component tree is the real one and only the
 * network is stubbed, from the same `e2e/fixtures/boardroom.ts` the 29 browser
 * journeys assert against. The stage timings below are paced for a human eye,
 * not sped up — the real pipeline lands these seven stages in about 4 seconds,
 * which is too fast to read.
 *
 *   npx tsx dashboard/scripts/record-boardroom-film.ts
 */

import { mkdir, readdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { chromium, type Page } from "playwright";
import { PERSONAS, PROOF_TOKEN, ROSTER, liveProof, progressPayload } from "../e2e/fixtures/boardroom";

const run = promisify(execFile);

const BASE = process.env.DECK_BASE_URL ?? "http://127.0.0.1:3000";
const OUT_DIR = path.resolve(import.meta.dirname, "../../submission/04-demo");
const RAW_DIR = path.resolve(import.meta.dirname, "../../.tmp/boardroom-film");
const SIZE = { width: 1440, height: 900 };

/** How long each stage is held on screen so a viewer can actually read it. */
const STAGE_HOLD_MS = 1500;

type Json = Record<string, unknown>;

/** Must run before any navigation: the page fetches personas and the roster on
 *  load, so a stub registered afterwards would arrive too late. */
async function stubStatic(page: Page) {
  await page.route("**/demo/personas", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(PERSONAS) }),
  );
  await page.route("**/demo/agents", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ROSTER) }),
  );
}

async function hideSkipLink(page: Page) {
  await page.addStyleTag({ content: ".skip-link { display: none !important; }" });
}

/** Act one: the visitor writes a complaint and watches seven stages land. */
async function recordRun(page: Page) {
  // The poll count drives how many stages have "landed", so the film shows the
  // boardroom filling one seat at a time rather than appearing all at once.
  let polls = 0;
  let firstPollAt = 0;
  await page.route("**/demo/live/*/progress", (route) => {
    const spokenCount = Math.min(polls++, 7);
    if (!firstPollAt) firstPollAt = Date.now();
    // The value panel reads `elapsed_seconds` from this payload while the header
    // clock counts the browser's own wall time. In production both come from the
    // same run, so the film must not let them drift apart on screen either.
    const elapsedSeconds = Number(((Date.now() - firstPollAt) / 1000).toFixed(2));
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        progressPayload({ spokenCount, state: spokenCount < 7 ? "RUNNING" : "COMPLETED", elapsedSeconds }),
      ),
    });
  });
  await page.route("**/demo/compose", () => {});

  await page.goto(`${BASE}/live`, { waitUntil: "networkidle" });
  await hideSkipLink(page);
  await page.waitForTimeout(1600);

  // Type the complaint so the film shows that the words are the visitor's.
  const body = page.getByLabel("What happened?");
  await body.click();
  await body.fill("");
  await body.pressSequentially(
    "A card payment left my account last night and I never approved it. My card never left my wallet. Please reverse it.",
    { delay: 26 },
  );
  await page.waitForTimeout(900);

  await page.getByRole("button", { name: "Run My Complaint Live" }).click();
  await page.locator(".board-minutes").waitFor();

  // Put the table in frame before the stages start landing. Without this the
  // film watches the form while the interesting thing happens below the fold.
  await page.locator(".boardroom").scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, -24));
  // Seven stages, held long enough to read each new line as it appears.
  await page.waitForTimeout(STAGE_HOLD_MS * 8);

  // Open one receipt: the answer to "how do we know that is not an animation?"
  await page.getByRole("button", { name: /^Core banking confirms the claim/ }).click();
  await page.waitForTimeout(2600);

  // Then the money: what the run handed back, and which numbers are assumptions.
  await page.locator(".value-ledger").scrollIntoViewIfNeeded();
  await page.waitForTimeout(3200);
}

/** Act two: the same pipeline refusing an injected instruction. */
async function recordRefusal(page: Page) {
  await page.route(`**/demo/live/${PROOF_TOKEN}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(liveProof({ quarantined: true }) as unknown as Json),
    }),
  );
  await page.goto(`${BASE}/live?run=${PROOF_TOKEN}`, { waitUntil: "networkidle" });
  await hideSkipLink(page);
  await page.locator(".boardroom.is-refused").waitFor();
  await page.waitForTimeout(3800);
  await page.locator(".value-ledger").scrollIntoViewIfNeeded();
  await page.waitForTimeout(2600);
}

async function main() {
  await rm(RAW_DIR, { recursive: true, force: true });
  await mkdir(RAW_DIR, { recursive: true });
  await mkdir(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: SIZE,
    deviceScaleFactor: 1,
    recordVideo: { dir: RAW_DIR, size: SIZE },
  });
  const page = await context.newPage();
  await stubStatic(page);

  console.log("Recording the run…");
  await recordRun(page);
  console.log("Recording the refusal…");
  await recordRefusal(page);

  await context.close();
  await browser.close();

  const [raw] = (await readdir(RAW_DIR)).filter((name) => name.endsWith(".webm"));
  if (!raw) throw new Error("Playwright produced no video.");
  const rawPath = path.join(RAW_DIR, raw);
  const webm = path.join(RAW_DIR, "boardroom-film.webm");
  await rename(rawPath, webm);

  // H.264 in an MP4 container, because that is what PowerPoint and Keynote will
  // both play without asking the presenter to install anything.
  const mp4 = path.join(OUT_DIR, "Axiom-Boardroom-Demo.mp4");
  console.log("Transcoding to H.264…");
  await run("ffmpeg", [
    "-y", "-i", webm,
    "-c:v", "libx264", "-preset", "slow", "-crf", "23",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    "-an", mp4,
  ]);

  // A poster frame, so the slide shows the boardroom rather than a black box
  // before anyone presses play. Taken late in the run, when the table is full.
  const poster = path.join(OUT_DIR, "Axiom-Boardroom-Demo-poster.png");
  await run("ffmpeg", ["-y", "-ss", "00:00:18", "-i", mp4, "-frames:v", "1", poster]);

  console.log(`Wrote ${mp4}`);
  console.log(`Wrote ${poster}`);
}

main().catch((reason) => {
  console.error(reason);
  process.exit(1);
});
