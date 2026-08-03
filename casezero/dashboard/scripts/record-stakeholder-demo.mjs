import { chromium } from "playwright";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { demoSceneById } from "./demo-scenes.mjs";

const baseURL = process.env.DEMO_BASE_URL || "http://127.0.0.1:3000";
const projectRoot = path.resolve(process.cwd(), "..");
const outputDir = path.join(projectRoot, "submission/04-demo");
const outputFile = path.join(outputDir, "casezero-stakeholder-demo-raw.webm");
const timelineFile = path.join(outputDir, "casezero-demo-timeline.json");
const slideDir = path.join(projectRoot, "submission/02-deck/final-verified-render");
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const timeline = [];
let recordingStartedAt = 0;

async function installDemoChrome(page) {
  await page.evaluate(() => {
    document.querySelectorAll(".demo-chrome").forEach((node) => node.remove());
    const style = document.createElement("style");
    style.className = "demo-chrome";
    style.textContent = `
      .demo-cursor { position: fixed; width: 24px; height: 24px; z-index: 2147483646; border: 2px solid #8b2333; background: rgba(242,245,242,.84); border-radius: 50%; pointer-events: none; transform: translate(-50%,-50%); box-shadow: 0 0 0 5px rgba(139,35,51,.13); }
      .demo-click-ripple { position: fixed; width: 24px; height: 24px; z-index: 2147483645; border: 2px solid #8b2333; border-radius: 50%; pointer-events: none; transform: translate(-50%,-50%); animation: demo-ripple 760ms cubic-bezier(.22,.8,.2,1) forwards; }
      .demo-caption { position: fixed; z-index: 2147483644; left: 50%; bottom: 30px; width: min(1100px, calc(100vw - 96px)); transform: translateX(-50%); display: grid; grid-template-columns: 190px 1fr; gap: 20px; align-items: center; padding: 17px 22px; color: #e8eee9; background: rgba(11,15,12,.96); border: 1px solid #637268; border-left: 4px solid #8b2333; box-shadow: 0 18px 70px rgba(11,15,12,.25); pointer-events: none; }
      .demo-caption small { color: #a8bfb0; font: 700 11px/1.35 Menlo, monospace; letter-spacing: .09em; text-transform: uppercase; }
      .demo-caption strong { display: block; font: 700 23px/1.08 "Helvetica Neue", Arial, sans-serif; letter-spacing: -.025em; }
      .demo-caption span { display: block; margin-top: 5px; color: #b5c1b8; font: 500 14px/1.35 "Helvetica Neue", Arial, sans-serif; }
      @keyframes demo-ripple { to { transform: translate(-50%,-50%) scale(3.3); opacity: 0; } }
    `;
    document.head.appendChild(style);
    const cursor = document.createElement("span");
    cursor.className = "demo-cursor demo-chrome";
    document.body.appendChild(cursor);
    document.addEventListener("mousemove", (event) => {
      cursor.style.left = `${event.clientX}px`;
      cursor.style.top = `${event.clientY}px`;
    });
  });
}

async function setCaption(page, scene) {
  await page.evaluate((content) => {
    document.querySelector(".demo-caption")?.remove();
    const caption = document.createElement("div");
    caption.className = "demo-caption demo-chrome";
    caption.innerHTML = `<small>${content.kicker}</small><div><strong>${content.title}</strong><span>${content.caption}</span></div>`;
    document.body.appendChild(caption);
  }, scene);
}

async function visibleClick(page, locator, hold = 800) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error("Demo target has no visible bounds.");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y, { steps: 28 });
  await pause(hold);
  await page.evaluate(({ x: left, y: top }) => {
    const ripple = document.createElement("span");
    ripple.className = "demo-click-ripple demo-chrome";
    Object.assign(ripple.style, { left: `${left}px`, top: `${top}px` });
    document.body.appendChild(ripple);
    window.setTimeout(() => ripple.remove(), 780);
  }, { x, y });
  await page.mouse.click(x, y);
}

async function smoothScroll(page, top, settle = 1800) {
  await page.evaluate((target) => window.scrollTo({ top: target, behavior: "smooth" }), top);
  await pause(settle);
}

async function showSlide(page, number, scene) {
  const imagePath = path.join(slideDir, `slide-${number}.png`);
  const data = (await readFile(imagePath)).toString("base64");
  await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#0b0f0c}img{display:block;width:100vw;height:100vh;object-fit:cover}</style></head><body><img alt="${scene.title}" src="data:image/png;base64,${data}"></body></html>`);
  await installDemoChrome(page);
  await setCaption(page, scene);
}

async function gotoApp(page, route) {
  await page.goto(`${baseURL}${route}`, { waitUntil: "networkidle" });
  await installDemoChrome(page);
}

async function runScene(page, id, action) {
  const scene = demoSceneById[id];
  if (!scene) throw new Error(`Unknown scene: ${id}`);
  const start = Date.now();
  timeline.push({ ...scene, startMs: start - recordingStartedAt, endMs: null });
  await action(scene);
  const elapsed = Date.now() - start;
  await pause(Math.max(2500, scene.durationMs - elapsed));
  timeline.at(-1).endMs = Date.now() - recordingStartedAt;
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
    localStorage.setItem("casezero_tour", "complete");
  });

  const page = await context.newPage();
  const video = page.video();
  recordingStartedAt = Date.now();

  await runScene(page, "title", async (scene) => showSlide(page, 1, scene));
  await runScene(page, "pain", async (scene) => showSlide(page, 2, scene));
  await runScene(page, "architecture", async (scene) => showSlide(page, 4, scene));

  await runScene(page, "onboarding", async (scene) => {
    await gotoApp(page, "/");
    await setCaption(page, scene);
    await pause(2600);
    await smoothScroll(page, 650, 1500);
    await smoothScroll(page, 0, 1200);
  });

  await runScene(page, "human_queue", async (scene) => {
    await visibleClick(page, page.getByRole("button", { name: /Explore the operating workspace/ }));
    await page.waitForURL(/\/simple/);
    await installDemoChrome(page);
    await setCaption(page, scene);
    await pause(2500);
    await smoothScroll(page, 530, 1600);
  });

  await runScene(page, "mission_control", async (scene) => {
    await gotoApp(page, "/pro");
    await setCaption(page, scene);
    await pause(2200);
    await smoothScroll(page, 480, 1800);
    await smoothScroll(page, 1080, 1800);
    await smoothScroll(page, 0, 1400);
  });

  await runScene(page, "axiom", async (scene) => {
    await setCaption(page, scene);
    await visibleClick(page, page.getByRole("button", { name: "Open Axiom operating agent" }));
    const command = page.getByLabel("What needs to happen?");
    await command.fill("");
    await command.pressSequentially("Verify MYB-2026-000012", { delay: 72 });
    await visibleClick(page, page.getByRole("button", { name: "Prepare action" }));
    await pause(4300);
  });

  await runScene(page, "customer", async (scene) => {
    await gotoApp(page, "/proactive/demo-proactive-techworld-2026");
    await setCaption(page, scene);
    await pause(2500);
    await visibleClick(page, page.getByRole("button", { name: "Not me — dispute it" }));
    await pause(4300);
    await visibleClick(page, page.getByRole("link", { name: "Open complaint tracker" }));
    await page.waitForURL(/\/track\//);
    await installDemoChrome(page);
    await setCaption(page, scene);
    await pause(2600);
  });

  await runScene(page, "audit", async (scene) => {
    await gotoApp(page, "/audit");
    await setCaption(page, scene);
    await pause(2000);
    await visibleClick(page, page.getByRole("button", { name: "Tamper sequence 04" }));
    await pause(3800);
    await gotoApp(page, "/quarantine");
    await setCaption(page, scene);
    await pause(2800);
  });

  await runScene(page, "settings", async (scene) => {
    await gotoApp(page, "/settings");
    await setCaption(page, scene);
    await pause(2200);
    const warning = page.getByLabel("SLA warning horizon");
    await warning.fill("12");
    await visibleClick(page, page.getByRole("button", { name: "Rehearse control change" }));
    await pause(3300);
    await smoothScroll(page, 720, 1800);
  });

  await runScene(page, "operators", async (scene) => {
    await gotoApp(page, "/admin/users");
    await setCaption(page, scene);
    await page.getByLabel("Full name").fill("New Complaints Officer");
    await page.getByLabel("Work email", { exact: true }).fill("liaison@mybank.example");
    await pause(1400);
    await visibleClick(page, page.getByRole("button", { name: "Rehearse invitation" }));
    await pause(3400);
  });

  await runScene(page, "proof", async (scene) => showSlide(page, 8, scene));
  await runScene(page, "close", async (scene) => showSlide(page, 10, scene));

  await context.close();
  await video.saveAs(outputFile);
  await browser.close();
  await writeFile(timelineFile, `${JSON.stringify({ generatedAt: new Date().toISOString(), baseURL, video: outputFile, scenes: timeline }, null, 2)}\n`);
  console.log(`Demo recording saved to ${outputFile}`);
  console.log(`Timeline saved to ${timelineFile}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
