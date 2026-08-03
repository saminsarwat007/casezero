import { mkdir, readFile, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";

const projectRoot = path.resolve(process.cwd(), "..");
const demoDir = path.join(projectRoot, "submission/04-demo");
const rawVideo = path.join(demoDir, "casezero-stakeholder-demo-raw.webm");
const timelineFile = path.join(demoDir, "casezero-demo-timeline.json");
const outputVideo = path.join(demoDir, "CaseZero-Stakeholder-Demo.mp4");
const captionsFile = path.join(demoDir, "CaseZero-Stakeholder-Demo.en.vtt");
const timingsFile = path.join(demoDir, "CaseZero-Stakeholder-Demo-audio.json");
const audioDir = path.join(projectRoot, "tmp/demo-audio");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: "utf8", ...options });
  if (result.status !== 0) {
    throw new Error(`${command} failed (${result.status}):\n${result.stderr || result.stdout}`);
  }
  return result.stdout.trim();
}

function seconds(file) {
  return Number(run("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file]));
}

function vttTime(ms) {
  const total = Math.max(0, Math.round(ms));
  const hours = Math.floor(total / 3600000);
  const minutes = Math.floor((total % 3600000) / 60000);
  const secs = Math.floor((total % 60000) / 1000);
  const millis = total % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

async function main() {
  await mkdir(audioDir, { recursive: true });
  const timeline = JSON.parse(await readFile(timelineFile, "utf8"));
  const audio = [];

  for (const [index, scene] of timeline.scenes.entries()) {
    const file = path.join(audioDir, `${String(index + 1).padStart(2, "0")}-${scene.id}.aiff`);
    run("say", ["-v", "Daniel", "-r", "178", "-o", file, scene.narration]);
    const durationSec = seconds(file);
    const slotSec = (scene.endMs - scene.startMs) / 1000;
    const targetSec = Math.max(4, slotSec - 1.25);
    const tempo = Math.max(1, durationSec / targetSec);
    audio.push({ id: scene.id, file, durationSec, slotSec, targetSec, tempo, startMs: scene.startMs });
  }

  const inputs = audio.flatMap((item) => ["-i", item.file]);
  const filters = audio.map((item, index) => `[${index + 1}:a]atempo=${item.tempo.toFixed(5)},adelay=${Math.max(0, Math.round(item.startMs))}:all=1,volume=1.08[a${index}]`);
  const labels = audio.map((_, index) => `[a${index}]`).join("");
  filters.push(`${labels}amix=inputs=${audio.length}:duration=longest:normalize=0,alimiter=limit=0.95[mix]`);

  run("ffmpeg", [
    "-y",
    "-i", rawVideo,
    ...inputs,
    "-filter_complex", filters.join(";"),
    "-map", "0:v:0",
    "-map", "[mix]",
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "18",
    "-pix_fmt", "yuv420p",
    "-c:a", "aac",
    "-b:a", "192k",
    "-movflags", "+faststart",
    "-metadata", "title=CaseZero Stakeholder Demo",
    "-metadata", "comment=AI Agent Track · Case Study 1 · Axiom by CaseZero",
    "-shortest",
    outputVideo,
  ]);

  const vtt = ["WEBVTT", ""];
  timeline.scenes.forEach((scene, index) => {
    vtt.push(String(index + 1));
    vtt.push(`${vttTime(scene.startMs)} --> ${vttTime(scene.endMs)}`);
    vtt.push(`${scene.title}\n${scene.narration}`);
    vtt.push("");
  });
  await writeFile(captionsFile, `${vtt.join("\n")}\n`);
  await writeFile(timingsFile, `${JSON.stringify({ videoDurationSec: seconds(outputVideo), voice: "Daniel", rate: 178, scenes: audio }, null, 2)}\n`);
  console.log(`Narrated demo saved to ${outputVideo}`);
  console.log(`Captions saved to ${captionsFile}`);
  audio.forEach((item) => console.log(`${item.id}: voice ${item.durationSec.toFixed(1)}s / visual ${item.slotSec.toFixed(1)}s / tempo ${item.tempo.toFixed(2)}x`));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
