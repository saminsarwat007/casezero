import { expect, test } from "@playwright/test";

const response = {
  state: "COMPLETED",
  token: "live-proof-token-12345678901234567890",
  started_at: "2026-08-04T08:00:00+00:00",
  finished_at: "2026-08-04T08:00:04+00:00",
  proof: {
    execution: {
      token: "live-proof-token-12345678901234567890",
      case_ref: "MYB-2026-000501",
      started_at: "2026-08-04T08:00:00+00:00",
      completed_at: "2026-08-04T08:00:04+00:00",
      duration_ms: 4210,
      runtime: "Vercel",
      assurance: "VERIFIED_LIVE",
      reused: false,
      source: "SYNTHETIC_INPUT",
      execution_mode: "LIVE_EXECUTION",
    },
    input: {
      fixture: "unauthorised_transaction_v1",
      sender: "ahmad.live@example.my",
      subject: "Unauthorised card transaction",
      account_no_masked: "******6890",
      amount_rm: 2450,
      merchant: "TECHWORLD KL",
      txn_ref: "CZLIVE-20260804-ABC12345",
    },
    result: {
      status: "COMMUNICATED",
      outcome: "RESOLVED_IN_FULL",
      verification_result: "PASS",
      category: "unauthorized_transaction",
      urgency: "High",
      confidence: 0.97,
      posted: true,
      degraded: [],
    },
    stages: [
      ["intake", "Screen & extract", "INTAKE_EXTRACTED", 2],
      ["classify", "Classify complaint", "CLASSIFIED", 4],
      ["sla", "Apply urgency & SLA", "URGENCY_ASSIGNED", 5],
      ["verify", "Verify bank evidence", "VERIFICATION_COMPLETED", 7],
      ["gate", "Authorize action", "GATE_DECISION", 9],
      ["journal", "Post balanced journal", "JOURNAL_POSTED", 10],
      ["communicate", "Lint & release response", "MESSAGE_SENT", 13],
    ].map(([id, label, event_type, seq]) => ({
      id,
      label,
      status: "PASS",
      event_type,
      seq,
      actor: `agent:${id}`,
      recorded_at: "2026-08-04T08:00:03+00:00",
      hash: "e414ce2b6706843f0b79e60607d6f30402109127ec86c5925277fc4fc4e92aa1",
      evidence: `${label} returned checkable evidence.`,
    })),
    models: [
      { agent: "intake", provider: "gemini", model: "gemini-2.5-flash", tokens_in: 420, tokens_out: 80, latency_ms: 512, cost_rm: 0.001, metered: true },
      { agent: "classifier", provider: "gemini", model: "gemini-2.5-flash", tokens_in: 510, tokens_out: 94, latency_ms: 640, cost_rm: 0.001, metered: true },
    ],
    tools: [
      { server: "core-banking", tool: "verify_claim", transport: "stdio", latency_ms: 92, ok: true },
      { server: "core-banking", tool: "post_adjustment", transport: "stdio", latency_ms: 88, ok: true },
    ],
    journal: {
      balanced: true,
      entries: [{ entry_type: "REVERSAL", debit_account: "SUSPENSE:FRAUD", credit_account_masked: "******6890", amount_rm: 2450, posted_by: "agent:resolver", posted_at: "2026-08-04T08:00:03+00:00" }],
    },
    chain: { ok: true, links: 13, head_hash: "e414ce2b6706843f0b79e60607d6f30402109127ec86c5925277fc4fc4e92aa1", first_bad_seq: null, reason: null },
  },
};

test.beforeEach(async ({ page }) => {
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

test("one click renders a persisted live proof instead of rehearsal data", async ({ page }) => {
  await page.goto("/live");
  await page.getByRole("button", { name: "Run a Fresh Live Complaint" }).click();
  await expect(page).toHaveURL(/\/live\?run=live-proof-token/);
  await expect(page.getByRole("heading", { name: "MYB-2026-000501" })).toBeVisible();
  await expect(page.getByText("Verified Live")).toBeVisible();
  await expect(page.getByText("COMMUNICATED", { exact: true })).toBeVisible();
  await expect(page.getByText("13 LINKS · VALID")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Post balanced journal" })).toBeVisible();
  await expect(page.getByText("core-banking.post_adjustment")).toBeVisible();
  await expect(page.getByText("BALANCED · POSTED BY SIGNED AUTHORITY")).toBeVisible();
});

test("live proof stays legible without horizontal overflow on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/live?run=live-proof-token-12345678901234567890");
  await expect(page.getByRole("heading", { name: "MYB-2026-000501" })).toBeVisible();
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);
});
