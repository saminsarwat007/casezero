import { expect, test } from "@playwright/test";
import { PERSONAS, ROSTER, liveProof, progressPayload } from "./fixtures/boardroom";

// The payload shapes live in ./fixtures/boardroom so this spec and the boardroom
// spec cannot drift apart, and so the stage labels stay the ones `roster.py`
// actually emits rather than an older set that only these tests believed in.
const response = liveProof();
const personas = PERSONAS;

const progressAt = (done: number, state: "RUNNING" | "COMPLETED" | "FAILED" = "RUNNING") =>
  progressPayload({ spokenCount: done, state });

test.beforeEach(async ({ page }) => {
  await page.route("**/demo/personas", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(personas) });
  });
  await page.route("**/demo/agents", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ROSTER) });
  });
  await page.route("**/demo/live**", async (route) => {
    await route.fulfill({ status: route.request().method() === "POST" ? 201 : 200, contentType: "application/json", body: JSON.stringify(response) });
  });
});

test("public path explains the truth boundary before asking for a run", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Run a Live Complaint" })).toBeVisible();
  await page.getByRole("link", { name: "Run a Live Complaint" }).click();
  await expect(page.getByRole("heading", { name: "Watch one complaint become proof." })).toBeVisible();
  await expect(page.getByText("Synthetic Customer Input")).toBeVisible();
  await expect(page.getByText("Real API · Real Model · MCP Bank Tools · Real Supabase Writes")).toBeVisible();
  await expect(page.getByText("The evidence rail starts empty.")).toBeVisible();
});

test("the composer runs the stakeholder's own wording and streams real stages", async ({ page }) => {
  let polls = 0;
  await page.route("**/demo/live/*/progress", async (route) => {
    polls += 1;
    // A valid run 404s until admission passes and the run row is inserted.
    if (polls === 1) {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Live execution not found." }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(progressAt(Math.min(polls - 1, 7))) });
  });

  const submissions: string[] = [];
  await page.route("**/demo/compose", async (route) => {
    submissions.push(route.request().postDataBuffer()?.toString("utf8") ?? "");
    await new Promise((resolve) => setTimeout(resolve, 3000));
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(response) });
  });

  await page.goto("/live");
  await page.getByLabel("File it as").selectOption("7142001233");
  await page.getByLabel("Subject").fill("Card charge I never made");
  await page.getByLabel("What happened?").fill("A payment left my account last night and I never approved it. Please reverse it.");
  await page.getByRole("button", { name: "Run My Complaint Live" }).click();

  // The boardroom is the default view now, so the live stage feed is read there.
  // The checklist is still one click away and is asserted in boardroom.spec.ts.
  await expect(page.getByRole("region", { name: /^Boardroom/ })).toContainText("Check against bank records");
  await expect(page.getByRole("heading", { name: "MYB-2026-000501" })).toBeVisible();
  expect(submissions[0]).toContain("Card charge I never made");
  // The sender identity stays bound to the chosen fictional customer.
  expect(submissions[0]).toContain("siti.rahman@example.my");
  expect(submissions[0]).toContain("7142001233");
});

test("the composer refuses a real identifier verbatim instead of scrubbing it", async ({ page }) => {
  // A refused run never gets a row, so its progress endpoint 404s forever.
  await page.route("**/demo/live/*/progress", async (route) => {
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Live execution not found." }) });
  });
  await page.route("**/demo/compose", async (route) => {
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Identity numbers are never accepted through the public runner. Delete the NRIC and describe the dispute instead." }),
    });
  });

  await page.goto("/live");
  await page.getByLabel("What happened?").fill("My NRIC is 880101-14-5523 and a payment left my account without approval.");
  await page.getByRole("button", { name: "Run My Complaint Live" }).click();

  const refusal = page.getByRole("alert").filter({ hasText: "This complaint did not run." });
  await expect(refusal).toContainText("Identity numbers are never accepted");
  await expect(refusal).toContainText("Adjust the complaint above and submit it again.");
});

test("one click renders a persisted live proof instead of rehearsal data", async ({ page }) => {
  await page.goto("/live");
  await page.getByRole("tab", { name: /Use the sample/ }).click();
  await page.getByRole("button", { name: "Run a Fresh Live Complaint" }).click();
  await expect(page).toHaveURL(/\/live\?run=live-proof-token/);
  await expect(page.getByRole("heading", { name: "MYB-2026-000501" })).toBeVisible();
  await expect(page.getByText("Verified Live")).toBeVisible();
  await expect(page.getByText("COMMUNICATED", { exact: true })).toBeVisible();
  await expect(page.getByText("13 LINKS · VALID")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Move the money" })).toBeVisible();
  await expect(page.getByText("core-banking.post_adjustment")).toBeVisible();
  await expect(page.getByText("BALANCED · POSTED BY SIGNED AUTHORITY")).toBeVisible();
});

test("live proof stays legible without horizontal overflow on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/live?run=${response.token}`);
  await expect(page.getByRole("heading", { name: "MYB-2026-000501" })).toBeVisible();
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);
});
