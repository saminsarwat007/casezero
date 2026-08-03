import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseURL = process.env.DEMO_BASE_URL || "http://127.0.0.1:3000";
const outputDir = path.resolve(process.cwd(), "../proof/video");
const outputFile = path.join(outputDir, "casezero-stakeholder-demo.webm");
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function visibleClick(page, locator, hold = 650) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error("Demo target has no visible bounds.");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y, { steps: 22 });
  await pause(hold);
  await page.evaluate(({ x: left, y: top }) => {
    const ripple = document.createElement("span");
    ripple.className = "demo-click-ripple";
    Object.assign(ripple.style, { left: `${left}px`, top: `${top}px` });
    document.body.appendChild(ripple);
    window.setTimeout(() => ripple.remove(), 720);
  }, { x, y });
  await page.mouse.click(x, y);
}

async function smoothScroll(page, top) {
  await page.evaluate((target) => window.scrollTo({ top: target, behavior: "smooth" }), top);
  await pause(1700);
}

async function main() {
  await mkdir(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: outputDir, size: { width: 1920, height: 1080 } },
  });
  await context.addInitScript(() => {
    localStorage.setItem("casezero_rehearsal", "1");
    localStorage.removeItem("casezero_tour");
    window.addEventListener("DOMContentLoaded", () => {
      const style = document.createElement("style");
      style.textContent = `
        .demo-cursor { position: fixed; width: 22px; height: 22px; z-index: 2147483646; border: 2px solid #8b2333; background: rgba(242,245,242,.76); border-radius: 50%; pointer-events: none; transform: translate(-50%,-50%); box-shadow: 0 0 0 4px rgba(139,35,51,.12); }
        .demo-click-ripple { position: fixed; width: 22px; height: 22px; z-index: 2147483645; border: 2px solid #8b2333; border-radius: 50%; pointer-events: none; transform: translate(-50%,-50%); animation: demo-ripple 700ms cubic-bezier(.22,.8,.2,1) forwards; }
        @keyframes demo-ripple { to { transform: translate(-50%,-50%) scale(3); opacity: 0; } }
      `;
      document.head.appendChild(style);
      const cursor = document.createElement("span");
      cursor.className = "demo-cursor";
      document.body.appendChild(cursor);
      document.addEventListener("mousemove", (event) => {
        cursor.style.left = `${event.clientX}px`;
        cursor.style.top = `${event.clientY}px`;
      });
    }, { once: true });
  });

  const page = await context.newPage();
  const video = page.video();

  await page.goto(baseURL, { waitUntil: "networkidle" });
  await pause(2800);
  await smoothScroll(page, 690);
  await pause(1800);
  await smoothScroll(page, 0);
  await visibleClick(page, page.getByRole("button", { name: /Explore the operating workspace/ }));
  await page.waitForURL(/\/simple/);
  await pause(2600);

  await visibleClick(page, page.getByRole("button", { name: "Show cases at risk" }));
  await pause(900);
  await visibleClick(page, page.getByRole("button", { name: "Prepare action" }));
  await pause(2500);
  await visibleClick(page, page.getByRole("button", { name: "Close Wajar" }), 350);
  await pause(900);

  await visibleClick(page, page.getByRole("navigation").getByRole("link", { name: /Mission control/ }));
  await page.waitForURL(/\/pro$/);
  await pause(2600);
  await smoothScroll(page, 490);
  await pause(1800);
  await smoothScroll(page, 0);

  await visibleClick(page, page.getByRole("button", { name: "Open Wajar operating agent" }));
  const command = page.getByLabel("What needs to happen?");
  await command.fill("");
  await command.pressSequentially("Verify MYB-2026-000012", { delay: 55 });
  await visibleClick(page, page.getByRole("button", { name: "Prepare action" }));
  await pause(2800);
  await visibleClick(page, page.getByRole("button", { name: "Close Wajar" }), 350);

  await visibleClick(page, page.getByRole("navigation").getByRole("link", { name: /Customer alert/ }));
  await page.waitForURL(/\/proactive\//);
  await pause(2200);
  await visibleClick(page, page.getByRole("button", { name: "Not me — dispute it" }));
  await pause(3200);

  await page.goto(`${baseURL}/audit`, { waitUntil: "networkidle" });
  await pause(2200);
  await visibleClick(page, page.getByRole("button", { name: "Tamper sequence 04" }));
  await pause(3000);

  await visibleClick(page, page.getByRole("navigation").getByRole("link", { name: /Settings/ }));
  await page.waitForURL(/\/settings$/);
  await pause(2200);
  const warning = page.getByLabel("SLA warning horizon");
  await warning.fill("12");
  await visibleClick(page, page.getByRole("button", { name: "Rehearse control change" }));
  await pause(2800);
  await smoothScroll(page, 720);
  await pause(2200);

  await context.close();
  await video.saveAs(outputFile);
  await browser.close();
  console.log(`Demo recording saved to ${outputFile}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
