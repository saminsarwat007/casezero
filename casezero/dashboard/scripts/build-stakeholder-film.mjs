import { chromium } from "playwright";
import { createServer } from "node:http";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const projectRoot = path.resolve(import.meta.dirname, "../..");
const sourceHtml = path.join(import.meta.dirname, "stakeholder-film.html");
const outputDir = path.join(projectRoot, "submission/04-demo");
const tempDir = path.join(projectRoot, ".tmp/stakeholder-film");
const rawDir = path.join(tempDir, "raw");
const audioDir = path.join(tempDir, "audio");
const outputVideo = path.join(outputDir, "CaseZero-Stakeholder-Film.mp4");
const outputPoster = path.join(outputDir, "CaseZero-Stakeholder-Film-poster.png");
const outputContactSheet = path.join(outputDir, "CaseZero-Stakeholder-Film-contact-sheet.png");
const outputCaptions = path.join(outputDir, "CaseZero-Stakeholder-Film.en.vtt");
const outputScript = path.join(outputDir, "CaseZero-Stakeholder-Film-script.md");
const duration = 87;

const narration = [
  { id: "hook", start: 0.45, end: 7.5, text: "Bank complaints lose time between email, PDFs, core banking, CRM, and a policy clock that never stops." },
  { id: "collapse", start: 8.25, end: 14.5, text: "CaseZero turns those handoffs into one governed chain of evidence." },
  { id: "input", start: 15.25, end: 24.4, text: "A customer writes in their own words and can attach their own PDF. The original input is preserved before any agent begins." },
  { id: "agents", start: 25.1, end: 41.4, text: "Six specialists get to work. Intake structures it. Classifier identifies the issue. Verifier checks bank records. Resolver drafts the remedy. Communicator writes the update. Supervisor watches the deadline. Each seat has one job, and a visible boundary." },
  { id: "kernel", start: 42.15, end: 50.5, text: "The brain is deliberately split. AI proposes. Policy decides. Money needs verified evidence, a signed instruction, and a balanced journal." },
  { id: "human", start: 51.15, end: 59.5, text: "The human never disappears. Unclear, high-value, or policy-sensitive cases stop here for approval, rejection, or more information." },
  { id: "dashboard", start: 60.15, end: 67.5, text: "Stakeholders see the whole operation: workload, deadlines, agent health, the human queue, and every handoff." },
  { id: "proof", start: 68.15, end: 76.5, text: "One verified production run finished in twenty point one seconds: fourteen linked events, three model calls, three bank calls, and a balanced posting." },
  { id: "close", start: 77.15, end: 86.4, text: "Fewer handoffs. Faster answers. More control. Scan the QR code and try CaseZero with your own complaint and your own PDF." },
];

function run(command, args, options = {}) {
  return execFileSync(command, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], ...options }).trim();
}

function probeSeconds(file) {
  return Number(run("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file]));
}

function vttTime(seconds) {
  const ms = Math.max(0, Math.round(seconds * 1000));
  const hours = Math.floor(ms / 3600000);
  const minutes = Math.floor((ms % 3600000) / 60000);
  const secs = Math.floor((ms % 60000) / 1000);
  const millis = ms % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function contentType(file) {
  if (file.endsWith(".html")) return "text/html; charset=utf-8";
  if (file.endsWith(".png")) return "image/png";
  if (file.endsWith(".mp4")) return "video/mp4";
  return "application/octet-stream";
}

async function startServer() {
  const html = await readFile(sourceHtml);
  const server = createServer(async (request, response) => {
    try {
      const pathname = decodeURIComponent(new URL(request.url, "http://127.0.0.1").pathname);
      const file = pathname === "/" ? sourceHtml : path.resolve(projectRoot, `.${pathname}`);
      if (file !== sourceHtml && !file.startsWith(`${projectRoot}${path.sep}`)) throw new Error("Path outside project root");
      const bytes = file === sourceHtml ? html : await readFile(file);
      response.writeHead(200, { "Content-Type": contentType(file), "Cache-Control": "no-store" });
      response.end(bytes);
    } catch {
      response.writeHead(404);
      response.end("Not found");
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return { server, port: server.address().port };
}

async function recordFilm() {
  const { server, port } = await startServer();
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      recordVideo: { dir: rawDir, size: { width: 1920, height: 1080 } },
      reducedMotion: "no-preference",
    });
    const page = await context.newPage();
    const video = page.video();
    await page.goto(`http://127.0.0.1:${port}`, { waitUntil: "networkidle" });
    await page.waitForFunction(() => window.__filmReady === true, null, { timeout: 30000 });
    await page.evaluate(() => window.startFilm());
    await page.waitForFunction(() => window.__filmDone === true, null, { timeout: (duration + 10) * 1000 });
    await page.waitForTimeout(600);
    await context.close();
    const rawPath = await video.path();
    await browser.close();
    browser = null;
    return rawPath;
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

async function buildAudio() {
  const tracks = [];
  for (const [index, scene] of narration.entries()) {
    const aiff = path.join(audioDir, `${String(index + 1).padStart(2, "0")}-${scene.id}.aiff`);
    run("say", ["-v", "Daniel", "-r", "168", "-o", aiff, scene.text]);
    const sourceDuration = probeSeconds(aiff);
    const slot = scene.end - scene.start;
    const tempo = sourceDuration > slot ? sourceDuration / slot : 1;
    tracks.push({ ...scene, file: aiff, sourceDuration, tempo });
  }
  return tracks;
}

async function mux(rawVideo, tracks) {
  const voiceInputs = tracks.flatMap((track) => ["-i", track.file]);
  const filters = tracks.map((track, index) =>
    `[${index + 1}:a]atempo=${track.tempo.toFixed(5)},adelay=${Math.round(track.start * 1000)}:all=1,volume=1.05[v${index}]`,
  );
  const labels = tracks.map((_, index) => `[v${index}]`).join("");
  filters.push(`${labels}amix=inputs=${tracks.length}:duration=longest:normalize=0,highpass=f=70,acompressor=threshold=-18dB:ratio=2.2:attack=20:release=180,alimiter=limit=0.96[voice]`);
  filters.push(`anoisesrc=color=pink:amplitude=0.006:sample_rate=48000:d=${duration + 1},lowpass=f=900,highpass=f=80,afade=t=in:st=0:d=2,afade=t=out:st=${duration - 3}:d=3[air]`);
  filters.push(`sine=f=55:sample_rate=48000:d=${duration + 1},volume=0.012,afade=t=in:st=0:d=3,afade=t=out:st=${duration - 3}:d=3[tone]`);
  filters.push("[voice][air][tone]amix=inputs=3:duration=longest:normalize=0,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=7[mix]");

  run("ffmpeg", [
    "-y", "-i", rawVideo, ...voiceInputs,
    "-filter_complex", filters.join(";"),
    "-map", "0:v:0", "-map", "[mix]",
    "-t", String(duration), "-r", "30",
    "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
    "-movflags", "+faststart",
    "-metadata", "title=CaseZero — One complaint. One governed outcome.",
    "-metadata", "comment=Stakeholder product film using real CaseZero product footage and verified 12 Aug 2026 production metrics.",
    outputVideo,
  ]);
}

async function writeCompanionFiles(tracks) {
  const vtt = ["WEBVTT", ""];
  tracks.forEach((track, index) => {
    vtt.push(String(index + 1), `${vttTime(track.start)} --> ${vttTime(track.end)}`, track.text, "");
  });
  await writeFile(outputCaptions, `${vtt.join("\n")}\n`);

  const script = [
    "# CaseZero stakeholder film", "",
    "**Length:** 87 seconds  ",
    "**Audience:** banking stakeholders, hackathon judges and non-technical decision-makers  ",
    "**Core promise:** one complaint becomes one governed, inspectable outcome.", "",
    "## Voiceover and visual story", "",
    ...tracks.flatMap((track, index) => [
      `### ${index + 1}. ${track.id} — ${track.start.toFixed(1)}s to ${track.end.toFixed(1)}s`, "",
      track.text, "",
    ]),
    "## Claims shown", "",
    "- Visitors write their own complaint and may attach their own PDF; the original input is preserved.",
    "- Six bounded specialists prepare work; the deterministic policy kernel owns irreversible authority.",
    "- Humans approve, reject or request information for exceptions.",
    "- Production proof shown: case MYB-2026-000057, 20.1 seconds, 14 linked events, 3 model calls, 3 bank-tool calls, RM180.50 balanced posting.",
  ].join("\n");
  await writeFile(outputScript, `${script}\n`);
}

async function renderReviewAssets() {
  run("ffmpeg", ["-y", "-ss", "00:00:29", "-i", outputVideo, "-frames:v", "1", outputPoster]);
  run("ffmpeg", [
    "-y", "-i", outputVideo,
    "-vf", "fps=1/7.25,scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2:color=0x09110c,tile=4x3:padding=8:margin=8:color=0x09110c",
    "-frames:v", "1", outputContactSheet,
  ]);
}

async function main() {
  await rm(tempDir, { recursive: true, force: true });
  await mkdir(rawDir, { recursive: true });
  await mkdir(audioDir, { recursive: true });
  await mkdir(outputDir, { recursive: true });

  console.log("Recording the 1080p motion composition...");
  const rawVideo = await recordFilm();
  console.log("Generating and timing narration...");
  const tracks = await buildAudio();
  console.log("Mixing, encoding and adding fast-start metadata...");
  await mux(rawVideo, tracks);
  await writeCompanionFiles(tracks);
  await renderReviewAssets();

  console.log(`Wrote ${outputVideo}`);
  console.log(`Wrote ${outputPoster}`);
  console.log(`Wrote ${outputContactSheet}`);
  console.log(`Wrote ${outputCaptions}`);
  console.log(`Wrote ${outputScript}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
