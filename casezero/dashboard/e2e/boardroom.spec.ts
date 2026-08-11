import { expect, test, type Page } from "@playwright/test";
import {
  PERSONAS,
  PROOF_TOKEN,
  ROSTER,
  ROSTER_MISSING_GROQ,
  liveProof,
  progressPayload,
} from "./fixtures/boardroom";

/** These journeys guard the one claim the boardroom makes: that it is the audit
 *  trail rendered as speech, not a narration running beside it. Every assertion
 *  below is therefore about *restraint* — a seat that stays quiet, a stage that
 *  refuses to appear, a saving that is not claimed — because a decorative
 *  animation would pass a test that only checked for motion. */

type Options = { roster?: typeof ROSTER };

async function stubApi(page: Page, { roster = ROSTER }: Options = {}) {
  await page.route("**/demo/personas", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(PERSONAS) }),
  );
  await page.route("**/demo/agents", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(roster) }),
  );
}

/** Open a persisted proof. This is also the demo's Plan-B path: the boardroom has
 *  to redraw identically from a stored proof with no pipeline running. */
async function openProof(page: Page, proof: ReturnType<typeof liveProof>, options: Options = {}) {
  await stubApi(page, options);
  await page.route(`**/demo/live/${PROOF_TOKEN}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(proof) }),
  );
  await page.goto(`/live?run=${PROOF_TOKEN}`);
  await expect(page.getByRole("heading", { name: "MYB-2026-000501" })).toBeVisible();
}

/** Drive a run that is genuinely mid-flight: the compose POST is left open so the
 *  page renders from the progress feed alone, exactly as it does in the demo. */
async function openRunning(page: Page, progress: ReturnType<typeof progressPayload>, options: Options = {}) {
  await stubApi(page, options);
  await page.route("**/demo/live/*/progress", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(progress) }),
  );
  // Never fulfilled: the run is still executing for the whole of the assertion
  // window, so nothing here can be satisfied by the completed-proof rendering.
  await page.route("**/demo/compose", () => {});

  await page.goto("/live");
  await page.getByLabel("What happened?").fill(
    "A card payment left my account last night and I never approved it. Please reverse it.",
  );
  await page.getByRole("button", { name: "Run My Complaint Live" }).click();
  await expect(page.getByRole("region", { name: /^Boardroom/ })).toBeVisible();
}

test("the table is seated before a case exists, and says which seats have no brain", async ({ page }) => {
  await stubApi(page);
  await page.goto("/live");

  await expect(page.getByRole("heading", { name: "Models propose; the kernel disposes." })).toBeVisible();

  // All six agents plus the kernel are present and idle. The aria-label carries
  // the status, so the screen-reader path tells the same story as the dots.
  for (const name of ["Intake", "Classifier", "Verifier", "Resolver", "Communicator", "Supervisor"]) {
    await expect(page.getByRole("article", { name: `${name} — Waiting` })).toBeVisible();
  }
  await expect(page.getByText("Compliance Kernel")).toBeVisible();
  await expect(page.getByText("Awaiting case")).toBeVisible();

  // The two seats standing closest to the money must advertise no brain at all.
  await expect(page.getByRole("article", { name: /^Verifier/ })).toContainText("No model — deterministic");
  await expect(page.getByRole("article", { name: /^Resolver/ })).toContainText("No model — deterministic");
  // And a seat that does reason names the model that will actually run.
  await expect(page.getByRole("article", { name: /^Classifier/ })).toContainText("gemini / gemini-2.5-flash");

  // Nothing has happened, so there are no minutes to read yet.
  await expect(page.getByRole("heading", { name: "The minutes" })).toBeHidden();
});

test("a seat stays silent until its own event is on the chain", async ({ page }) => {
  // Three stages have landed. The remaining four have no event, so the boardroom
  // is forbidden from anticipating them even though it knows they are coming.
  await openRunning(page, progressPayload({ spokenCount: 3 }));

  const board = page.getByRole("region", { name: /^Boardroom/ });
  await expect(board).toContainText("Clean. English complaint, claiming RM2,450.00");
  await expect(board).toContainText("This is an unauthorised transaction. I am 97% confident.");
  await expect(board).toContainText("High priority. 5 working days under the BNM window");

  // The verifier's line is the next one due. It must not exist yet.
  await expect(board).not.toContainText("Core banking confirms the claim");
  await expect(board).not.toContainText("reversal posted");
  await expect(board).not.toContainText("Letter written and sent");

  // Unrun stages say why they are empty rather than showing a blank row.
  await expect(board).toContainText("Working. This line appears when its event is recorded.");
  await expect(board.getByText("Waiting for the case file.").first()).toBeVisible();
  await expect(page.getByText("3 / 7 handoffs")).toBeVisible();
});

test("clicking a spoken line produces its sequence number and hash", async ({ page }) => {
  await openProof(page, liveProof());

  // The bubble beside the speaking seat is the fast answer to "that is faked".
  const bubble = page.locator(".board-bubble button");
  await expect(bubble).toContainText("Letter written and sent.");
  await bubble.click();
  await expect(bubble).toHaveAttribute("aria-expanded", "true");

  const evidence = page.locator(".bubble-evidence");
  await expect(evidence).toContainText("RESOLVED_IN_FULL");
  await expect(evidence).toContainText("MESSAGE_SENT · SEQ 13 · e414ce2b670684…");

  // The same receipt is reachable from the minutes, which is the path that
  // survives on mobile where the bubble is not rendered.
  const verifyLine = page.getByRole("button", { name: /^Core banking confirms the claim/ });
  await verifyLine.click();
  const verifyEvidence = page.locator(".minute-evidence");
  await expect(verifyEvidence).toContainText("VERIFICATION_COMPLETED · SEQ 7");
  await expect(verifyEvidence).toContainText("e414ce2b6706843f0b…");
  // The seat that moved no money also reports that it never reasoned.
  await expect(verifyEvidence).toContainText("none — this seat compares records, it does not reason");
});

test("the model's own words are attributed to it, never stated as fact", async ({ page }) => {
  await openProof(page, liveProof());

  const classifyLine = page.getByRole("button", { name: /^This is an unauthorised transaction/ });
  await classifyLine.click();
  const evidence = page.locator(".minute-evidence");
  // The spoken line carries the category and confidence only. The sentence the
  // LLM actually wrote appears one level down, labelled as the model's.
  await expect(evidence).toContainText("Model's reasoning");
  await expect(evidence).toContainText("The sender denies authorising the card payment");
  await expect(classifyLine).not.toContainText("The sender denies authorising");
});

test("the kernel stamps rather than thinks, and the ruling is legible as a verdict", async ({ page }) => {
  await openProof(page, liveProof());

  await expect(page.locator(".kernel-stamp")).toContainText("AUTHORISED");
  await expect(page.locator(".kernel-block")).toContainText("No model. No thinking state. It snaps.");

  // Both gated transitions are on the kernel's own ledger, in order.
  const ledger = page.locator(".kernel-ledger li");
  await expect(ledger).toHaveCount(2);
  await expect(ledger.nth(0)).toContainText("BNM working-day window");
  await expect(ledger.nth(1)).toContainText("Financial gate");

  // A kernel row in the minutes is marked as a ruling, not as a remark.
  await expect(page.locator(".minute-mark").first()).toHaveText("AUTHORISED");
});

test("a quarantined run shows the refusal and claims nothing for it", async ({ page }) => {
  await openProof(page, liveProof({ quarantined: true }));

  await expect(page.getByRole("heading", { name: "Refused before any model call." })).toBeVisible();

  const stamp = page.locator(".kernel-stamp");
  await expect(stamp).toContainText("REFUSED");
  await expect(stamp).toContainText("Injection firewall");

  // Intake refused; nobody downstream was ever shown the message.
  await expect(page.getByRole("article", { name: "Intake — Refused the case" })).toBeVisible();
  for (const name of ["Classifier", "Verifier", "Resolver", "Communicator"]) {
    await expect(page.getByRole("article", { name: `${name} — Never saw it` })).toBeVisible();
  }
  // The supervisor is still on the deadline even for a refused case.
  await expect(page.getByRole("article", { name: "Supervisor — Watching deadlines" })).toBeVisible();

  const board = page.getByRole("region", { name: /^Boardroom/ });
  await expect(board).toContainText("I stopped before any model read this");
  await expect(board).toContainText("Never ran — the case was refused upstream.");

  // Zero model calls is the whole point of the moment, so the telemetry must agree.
  await expect(page.getByRole("heading", { name: "0 metered calls" })).toBeVisible();

  // A refusal saved no analyst minutes and must not pretend otherwise, even
  // though intake's stage did run and carries a 15-minute baseline.
  const value = page.getByRole("region", { name: /No savings claimed/ });
  await expect(value).toContainText("it spent nothing and it saved nothing");
  await expect(page.locator(".value-table")).toHaveCount(0);
});

test("the value panel keeps measured, baseline and assumption apart", async ({ page }) => {
  await openProof(page, liveProof());

  await expect(page.getByRole("heading", { name: "89.9 analyst minutes handed back." })).toBeVisible();

  // Per stage: the human desk replaced, the brief's baseline, and this run's
  // measured elapsed. The desk is what makes the number mean something.
  const verifyRow = page.getByRole("row", { name: /Check against bank records/ });
  await expect(verifyRow).toContainText("Investigator — logging into core banking and CRM");
  await expect(verifyRow).toContainText("25 min");
  await expect(verifyRow).toContainText("1.0s");

  // The case total only claims the stages that ran.
  const total = page.getByRole("row", { name: /Case total/ });
  await expect(total).toContainText("7 of 7 stages ran");
  await expect(total).toContainText("90 min");
  await expect(total).toContainText("4.2s");

  // Each tier is legible as a tier, so a judge can tell what we measured.
  const tiers = page.getByRole("region", { name: /analyst minutes handed back/ });
  await expect(tiers).toContainText("Timestamps on this run's hash chain");
  await expect(tiers).toContainText("The brief's 90 manual minutes, split per desk");
  await expect(tiers).toContainText("Editable below — never presented as fact");
});

test("the annual projection is driven by editable assumptions, not a fixed claim", async ({ page }) => {
  await openProof(page, liveProof());

  // Defaults: 89.9 measured minutes x 1200 complaints x 12 months / 60.
  await expect(page.getByText("21,576")).toBeVisible();
  // The rate defaults to the API's declared assumption rather than a constant.
  await expect(page.getByLabel("Analyst cost, RM per hour")).toHaveValue("24");
  await expect(page.getByRole("region", { name: /analyst minutes handed back/ })).toContainText("RM24/h");

  await page.getByLabel("Complaints per month").fill("2400");
  await expect(page.getByText("43,152")).toBeVisible();

  // An unusable assumption blanks the figure instead of showing a wrong one.
  await page.getByLabel("Complaints per month").fill("0");
  await expect(page.getByText("43,152")).toBeHidden();
});

test("a fallback is disclosed instead of advertising a brain that is not running", async ({ page }) => {
  await openProof(page, liveProof({ roster: ROSTER_MISSING_GROQ }), { roster: ROSTER_MISSING_GROQ });

  const communicator = page.getByRole("article", { name: /^Communicator/ });
  await expect(communicator).toContainText("gemini / gemini-2.5-flash");
  await expect(communicator).toContainText("Intended groq; running gemini — no groq key on this deployment");
  await expect(communicator).not.toContainText("llama");
});

test("a reopened proof says so rather than passing itself off as a fresh run", async ({ page }) => {
  const proof = liveProof();
  proof.proof.execution.reused = true;
  await openProof(page, proof);
  await expect(page.getByRole("region", { name: /^Boardroom/ })).toContainText("reopened proof");
});

test.describe("reduced motion", () => {
  // `reducedMotion` is a context option in this Playwright version, not a
  // top-level test option.
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  test("falls back to the checklist and keeps the whole story", async ({ page }) => {
    await stubApi(page);
    await page.route("**/demo/live/*/progress", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(progressPayload({ spokenCount: 3 })),
      }),
    );
    await page.route("**/demo/compose", () => {});

    await page.goto("/live");
    await page.getByLabel("What happened?").fill(
      "A card payment left my account last night and I never approved it. Please reverse it.",
    );
    await page.getByRole("button", { name: "Run My Complaint Live" }).click();

    // The animated table is replaced by the pre-existing rail, not merely frozen.
    await expect(page.getByRole("heading", { name: "3 of 7 stages recorded." })).toBeVisible();
    await expect(page.getByRole("region", { name: /^Boardroom/ })).toBeHidden();
    await expect(page.getByRole("button", { name: "The checklist" })).toHaveAttribute("aria-pressed", "true");

    // The rail carries the same stage labels and the same value panel, so the
    // reduced-motion path loses the animation and none of the story.
    await expect(page.locator(".stage-rail")).toContainText("Check against bank records");
    await expect(page.getByRole("region", { name: /The meter is running/ })).toBeVisible();

    // Choosing the boardroom is still allowed — reduced motion sets the default,
    // it does not remove the view.
    await page.getByRole("button", { name: "The boardroom" }).click();
    await expect(page.getByRole("region", { name: /^Boardroom/ })).toBeVisible();
  });
});

test("the boardroom relays vertically at 390px with no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openProof(page, liveProof());

  await expect(page.getByRole("region", { name: /^Boardroom/ })).toBeVisible();
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);

  // The floating bubble cannot be positioned honestly this narrow, so it is
  // dropped and the minutes carry the dialogue instead.
  await expect(page.locator(".board-bubble")).toBeHidden();
  const line = page.getByRole("button", { name: /^Core banking confirms the claim/ });
  await expect(line).toBeVisible();
  await line.click();
  await expect(page.locator(".minute-evidence")).toContainText("SEQ 7");
});
