import { expect, test } from "@playwright/test";

async function rehearsal(page: import("@playwright/test").Page) {
  await page.addInitScript(() => localStorage.setItem("casezero_rehearsal", "1"));
}

test("first visit onboards a stakeholder into a safe operating shift", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /The complaint arrives/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /See it work/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /One work email/ })).toBeVisible();
  await page.getByRole("link", { name: /Explore the Operations Workspace/ }).click();
  await expect(page).toHaveURL(/\/simple\?tour=1$/);
  await expect(page.getByRole("heading", { name: "Start with the cases that need a person." })).toBeVisible();
});

test("login opens a labelled offline operating ledger", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Open offline rehearsal" }).click();
  await expect(page).toHaveURL(/\/simple$/);
  await expect(page.getByRole("heading", { name: "Only three cases need you." })).toBeVisible();
  await expect(page.getByText("Synthetic rehearsal register")).toBeVisible();
});

test("mission control exposes pipeline, agents and measured evals", async ({ page }) => {
  await rehearsal(page);
  await page.goto("/pro");
  await expect(page.getByRole("heading", { name: "Operational pulse" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Case movement" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Agent theater" })).toBeVisible();
  await expect(page.getByText("95.90%")).toBeVisible();
  await expect(page.getByText("P50 / P95 4.63s")).toBeVisible();
});

test("Axiom prepares a governed action and issues a rehearsal receipt", async ({ page }) => {
  await rehearsal(page);
  await page.goto("/pro");
  await page.getByRole("button", { name: "Open Axiom operating agent" }).click();
  await page.getByLabel("What needs to happen?").fill("Set SLA warning to 12 hours");
  await page.getByRole("button", { name: "Prepare action" }).click();
  await expect(page.getByRole("heading", { name: "Change an operating control" })).toBeVisible();
  await expect(page.getByText("Admin role", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Confirm and execute/ }).click();
  await expect(page.getByRole("status")).toContainText("AXR-");
  await expect(page.getByRole("status")).toContainText("no live control changed", { ignoreCase: true });
});

test("mobile Pro uses a real menu and one-stage case view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await rehearsal(page);
  await page.goto("/pro");
  await page.getByRole("button", { name: "Open workspace menu" }).click();
  await expect(page.getByRole("link", { name: /Settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Close workspace menu" }).click();
  await page.getByRole("tab", { name: /CLASSIFIED/ }).click();
  await expect(page.getByRole("tab", { name: /CLASSIFIED/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("RM 12,000.00")).toBeVisible();
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);
});

test("stakeholder settings are usable and governed in rehearsal", async ({ page }) => {
  await rehearsal(page);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "What automation may do" })).toBeVisible();
  await page.getByLabel("SLA warning horizon").fill("12");
  await page.getByRole("button", { name: "Rehearse control change" }).click();
  await expect(page.getByRole("status")).toContainText("No live setting");
  await expect(page.getByText("04 append-only change receipts")).toBeVisible();
});

test("review queue supports the A keyboard decision", async ({ page }) => {
  await rehearsal(page);
  await page.goto("/review");
  await expect(page.getByRole("heading", { name: "Decide with the evidence assembled." })).toBeVisible();
  await page.keyboard.press("a");
  await expect(page.getByRole("status")).toContainText("APPROVE rehearsed");
});

test("policy studio simulates all changes before governance", async ({ page }) => {
  await rehearsal(page);
  await page.goto("/policy");
  await page.getByRole("button", { name: "Interpret and simulate" }).click();
  await expect(page.getByText("44-case category replay / 200-case corpus")).toBeVisible();
  await expect(page.getByText("PROPOSAL CHAIN VERIFIED")).toBeVisible();
  await page.getByRole("button", { name: "Apply as Compliance" }).click();
  await expect(page.getByText("APPLIED · V2")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("No live policy changed");
});

test("proactive alert files itself then opens the tracker", async ({ page }) => {
  await rehearsal(page);
  await page.goto("/proactive/demo-proactive-techworld-2026");
  await expect(page.getByRole("heading", { name: "Was this you?" })).toBeVisible();
  await page.getByRole("button", { name: "Not me — dispute it" }).click();
  await expect(page.getByText("FINANCIALLY RESOLVED")).toBeVisible();
  await page.getByRole("link", { name: "Open complaint tracker" }).click();
  await expect(page.getByRole("heading", { name: "MYB-2026-000012" })).toBeVisible();
});

test("audit rehearsal names the altered sequence and shows VOID", async ({ page }) => {
  await rehearsal(page);
  await page.goto("/audit");
  await page.getByRole("button", { name: "Tamper sequence 04" }).click();
  await expect(page.getByRole("heading", { name: "Integrity failure at sequence 04" })).toBeVisible();
  await expect(page.getByText("VOID", { exact: true })).toBeVisible();
});

test("operators makes email access clear without sending in rehearsal", async ({ page }) => {
  await rehearsal(page);
  await page.goto("/admin/users");
  await expect(page.getByRole("heading", { name: "Invite work emails. Assign least privilege." })).toBeVisible();
  await page.getByLabel("Full name").fill("New Complaints Officer");
  await page.getByLabel("Work email", { exact: true }).fill("liaison@mybank.example");
  await page.getByRole("button", { name: "Rehearse invitation" }).click();
  await expect(page.getByRole("status")).toContainText("No email was sent");
  await expect(page.getByText("liaison@mybank.example", { exact: true })).toBeVisible();
});
