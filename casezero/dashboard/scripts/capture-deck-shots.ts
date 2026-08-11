/** Capture the deck's screenshots from the real dashboard, not a mockup.
 *
 * The page under the camera is the deployed component tree. What is stubbed is
 * only the network: the API responses come from `e2e/fixtures/boardroom.ts`,
 * which mirrors `api/agents/roster.py` and `api/agents/handoff.py` field for
 * field and is the same data the 29 browser journeys assert against. So a shot
 * in the deck cannot show a layout the product does not really produce.
 *
 * Run against a dev or production server:
 *   npx tsx dashboard/scripts/capture-deck-shots.ts
 *   npx tsx dashboard/scripts/capture-deck-shots.ts http://127.0.0.1:3001
 *   DECK_BASE_URL=https://casezero-alpha.vercel.app npx tsx dashboard/scripts/capture-deck-shots.ts
 */

import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium, type Browser, type Page } from "playwright";
import {
  PERSONAS,
  PROOF_TOKEN,
  ROSTER,
  liveProof,
  progressPayload,
} from "../e2e/fixtures/boardroom";

const BASE = process.argv[2] ?? process.env.DECK_BASE_URL ?? "http://127.0.0.1:3000";
const OUT = path.resolve(import.meta.dirname, "../../submission/assets/deck");

/** 2x so the images stay crisp when a slide scales them up on a projector. */
const DESKTOP = { width: 1440, height: 960, deviceScaleFactor: 2 };
const MOBILE = { width: 390, height: 844, deviceScaleFactor: 3 };

type Json = Record<string, unknown>;

async function stub(page: Page, routes: Array<[string, Json]>) {
  for (const [glob, body] of routes) {
    await page.route(glob, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) }),
    );
  }
}

async function settle(page: Page) {
  // The skip link is `position: fixed` and only visible on focus, but Playwright
  // composites it into a clipped element screenshot. Hide it for the camera only.
  await page.addStyleTag({ content: ".skip-link { display: none !important; }" });
  // Let the entrance transitions finish so nothing is caught mid-fade.
  await page.waitForTimeout(900);
  // Next's development badge lives in a shadow root, so page CSS cannot hide
  // it. It is tooling, not product UI, and must never be baked into deck art.
  await page.evaluate(() => document.querySelector("nextjs-portal")?.remove());
}

async function shot(page: Page, name: string, selector?: string) {
  const target = selector ? page.locator(selector).first() : page;
  await target.screenshot({ path: path.join(OUT, `${name}.png`) });
  console.log(`  captured ${name}.png`);
}

async function shotFold(page: Page, name: string, selector: string, height: number) {
  const target = page.locator(selector).first();
  const originalStyle = await target.getAttribute("style");
  await target.evaluate((element, maxHeight) => {
    const html = element as HTMLElement;
    html.style.height = `${maxHeight}px`;
    html.style.maxHeight = `${maxHeight}px`;
    html.style.overflow = "hidden";
  }, height);
  await target.screenshot({ path: path.join(OUT, `${name}.png`) });
  await target.evaluate((element, style) => {
    if (style == null) element.removeAttribute("style");
    else element.setAttribute("style", style);
  }, originalStyle);
  console.log(`  captured ${name}.png`);
}

/** A completed PASS run, reopened from its persisted proof. */
async function captureCompleted(browser: Browser) {
  const page = await (await browser.newContext({ viewport: DESKTOP, deviceScaleFactor: 2 })).newPage();
  await stub(page, [
    ["**/demo/personas", PERSONAS as unknown as Json],
    ["**/demo/agents", ROSTER as unknown as Json],
    [`**/demo/live/${PROOF_TOKEN}`, liveProof() as unknown as Json],
  ]);

  await page.goto(`${BASE}/live?run=${PROOF_TOKEN}`, { waitUntil: "networkidle" });
  await page.locator(".boardroom").waitFor();
  await settle(page);
  await shot(page, "boardroom-complete", ".boardroom");
  await shot(page, "value-ledger", ".value-ledger");

  // The click-through: one spoken line opened to its sequence number and hash.
  await page.getByRole("button", { name: /^Core banking confirms the claim/ }).click();
  await page.waitForTimeout(320);
  await shot(page, "receipt-open", ".board-minutes");

  await page.close();
}

/** The refusal. This is the slide that wins the room, so it gets its own shot. */
async function captureRefusal(browser: Browser) {
  const page = await (await browser.newContext({ viewport: DESKTOP, deviceScaleFactor: 2 })).newPage();
  const proof = liveProof({ quarantined: true });
  await stub(page, [
    ["**/demo/personas", PERSONAS as unknown as Json],
    ["**/demo/agents", ROSTER as unknown as Json],
    [`**/demo/live/${PROOF_TOKEN}`, proof as unknown as Json],
  ]);

  await page.goto(`${BASE}/live?run=${PROOF_TOKEN}`, { waitUntil: "networkidle" });
  await page.locator(".boardroom.is-refused").waitFor();
  await settle(page);
  await shot(page, "boardroom-refused", ".boardroom");
  await shot(page, "value-refused", ".value-ledger");
  await page.close();
}

/** Mid-flight, so the deck can show that unrun stages stay visibly silent. */
async function captureRunning(browser: Browser) {
  const page = await (await browser.newContext({ viewport: DESKTOP, deviceScaleFactor: 2 })).newPage();
  await stub(page, [
    ["**/demo/personas", PERSONAS as unknown as Json],
    ["**/demo/agents", ROSTER as unknown as Json],
    ["**/demo/live/*/progress", progressPayload({ spokenCount: 4 }) as unknown as Json],
  ]);
  // Never resolved: the run stays open for the duration of the capture.
  await page.route("**/demo/compose", () => {});

  await page.goto(`${BASE}/live`, { waitUntil: "networkidle" });
  await shot(page, "composer", ".live-input");
  await shot(page, "boardroom-idle", ".boardroom");

  await page
    .getByLabel("What happened?")
    .fill("A card payment left my account last night and I never approved it. Please reverse it.");
  await page.getByRole("button", { name: "Run My Complaint Live" }).click();
  await page.locator(".board-minutes").waitFor();
  await settle(page);
  await shot(page, "boardroom-running", ".boardroom");
  await page.close();
}

/** 390px, because "works on mobile" is an accessibility claim we have to show. */
async function captureMobile(browser: Browser) {
  const page = await (await browser.newContext({ viewport: MOBILE, deviceScaleFactor: 3, isMobile: true, hasTouch: true })).newPage();
  await stub(page, [
    ["**/demo/personas", PERSONAS as unknown as Json],
    ["**/demo/agents", ROSTER as unknown as Json],
    [`**/demo/live/${PROOF_TOKEN}`, liveProof() as unknown as Json],
  ]);
  await page.goto(`${BASE}/live?run=${PROOF_TOKEN}`, { waitUntil: "networkidle" });
  await page.locator(".boardroom").waitFor();
  await settle(page);
  await shotFold(page, "boardroom-mobile-fold", ".boardroom", MOBILE.height);
  await shot(page, "boardroom-mobile", ".boardroom");
  await page.close();
}

/** The public landing page, for the opening slide. */
async function captureLanding(browser: Browser) {
  const page = await (await browser.newContext({ viewport: DESKTOP, deviceScaleFactor: 2 })).newPage();
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await settle(page);
  await shot(page, "landing");
  await page.close();
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();
  try {
    console.log(`Capturing from ${BASE} into ${OUT}`);
    await captureLanding(browser);
    await captureRunning(browser);
    await captureCompleted(browser);
    await captureRefusal(browser);
    await captureMobile(browser);
  } finally {
    await browser.close();
  }
  console.log("Done.");
}

main().catch((reason) => {
  console.error(reason);
  process.exit(1);
});
