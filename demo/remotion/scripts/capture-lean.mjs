// Lean footage capture with Playwright (Google Chrome stable, no download needed).
// Records the live site at 1920x1080 and converts each clip to H.264 mp4 in public/clips.
// Existing clips are never overwritten, so this can run alongside another capture pass.
import { chromium } from 'playwright';
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const BASE = process.env.CAPTURE_BASE || 'https://useaetheris.vercel.app';
const OUT = path.resolve('public/clips');
const TMP = path.resolve('clips/tmp');
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(TMP, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function scrollBy(page, px, { step = 5, every = 16 } = {}) {
  const n = Math.round(Math.abs(px) / step);
  const dir = px < 0 ? -1 : 1;
  for (let i = 0; i < n; i++) { await page.mouse.wheel(0, dir * step); await sleep(every); }
}

async function record(name, seconds, run) {
  const target = path.join(OUT, `${name}.mp4`);
  if (fs.existsSync(target)) { console.log(`${name}: already present, skipping`); return; }
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const dir = path.join(TMP, name);
  fs.rmSync(dir, { recursive: true, force: true });
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, colorScheme: 'dark',
    recordVideo: { dir, size: { width: 1920, height: 1080 } },
  });
  const page = await ctx.newPage();
  const started = Date.now();
  try { await run(page); } catch (e) { console.log(`${name}: ${e.message.split('\n')[0]}`); }
  const remaining = seconds * 1000 - (Date.now() - started);
  if (remaining > 0) await sleep(remaining);
  await ctx.close();
  await browser.close();
  const webm = fs.readdirSync(dir).find((f) => f.endsWith('.webm'));
  execSync(`ffmpeg -y -loglevel error -i "${path.join(dir, webm)}" -r 30 -c:v libx264 -preset medium -crf 16 -pix_fmt yuv420p -vf scale=1920:1080 -an "${target}"`);
  const d = execSync(`ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "${target}"`).toString().trim();
  console.log(`${name}: ${Number(d).toFixed(1)}s -> public/clips/${name}.mp4`);
}

await record('landing', 28, async (page) => {
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.mouse.move(960, 540);
  await sleep(2500);
  for (let i = 0; i < 6; i++) { await scrollBy(page, 900); await sleep(1400); }
});

await record('dashboard', 32, async (page) => {
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle' });
  await page.getByText('Live', { exact: true }).first().waitFor({ timeout: 30000 });
  await page.mouse.move(960, 540);
  await sleep(3000);
  await scrollBy(page, 520); await sleep(1200);
  // Expand the newest job row so the sub-agent assignment with its HCS anchor is visible.
  const expander = page.locator('table button').first();
  if (await expander.count()) { await expander.click({ timeout: 5000 }); await sleep(3200); }
  await scrollBy(page, 700); await sleep(1500);
  await scrollBy(page, 800); await sleep(1500);
  await scrollBy(page, 900); await sleep(1500);
  await scrollBy(page, 900); await sleep(2000);
});

await record('brief', 20, async (page) => {
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle' });
  await page.getByText('Live', { exact: true }).first().waitFor({ timeout: 30000 });
  await page.mouse.move(960, 540);
  await sleep(1200);
  await page.locator('[data-role="client"]').first().click();
  await sleep(1800);
  const title = page.getByPlaceholder('Security review of the escrow settlement path').first();
  await title.scrollIntoViewIfNeeded();
  await sleep(700);
  await title.click();
  await page.keyboard.type('Audit the settlement path for reentrancy and escrow over-commitment', { delay: 34 });
  const role = page.locator('select').filter({ hasText: /security-audit/ }).first();
  if (await role.count()) { await role.selectOption('security-audit'); await sleep(500); }
  const area = page.locator('textarea').first();
  await area.click();
  await page.keyboard.type('Review AetherisAgency and AetherisTreasury for reentrancy, over-commitment of the escrowed deposit and settlement ordering. Return findings ranked by severity, each with the function and line, and a one-line fix.', { delay: 20 });
  await sleep(2500);
});

await record('docs', 12, async (page) => {
  await page.goto(`${BASE}/docs/agents`, { waitUntil: 'networkidle' });
  await page.mouse.move(960, 540);
  await sleep(1800);
  for (let i = 0; i < 4; i++) { await scrollBy(page, 700); await sleep(1200); }
});

console.log('capture done');
