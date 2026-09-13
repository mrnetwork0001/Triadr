// Footage capture with Playwright (Google Chrome stable). 1920x1080 -> H.264 in public/clips.
// LIVE base (credentials present, app cards green) is used for the landing and the idle console;
// SIM base is used for the fault scenarios, because a live run stops and waits for a human on Telegram.
import { chromium } from 'playwright'
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const LIVE = process.env.CAPTURE_LIVE || 'http://127.0.0.1:8771'
const SIM = process.env.CAPTURE_SIM || 'http://38.49.213.208:8791'
const OUT = path.resolve('public/clips')
const TMP = path.resolve('clips/tmp')
fs.mkdirSync(OUT, { recursive: true }); fs.mkdirSync(TMP, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function scrollBy(page, px, { step = 6, every = 16 } = {}) {
  const n = Math.round(Math.abs(px) / step), dir = px < 0 ? -1 : 1
  for (let i = 0; i < n; i++) { await page.mouse.wheel(0, dir * step); await sleep(every) }
}

async function record(name, seconds, run) {
  const target = path.join(OUT, `${name}.mp4`)
  if (fs.existsSync(target)) { console.log(`${name}: present, skipping`); return }
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  const dir = path.join(TMP, name)
  fs.rmSync(dir, { recursive: true, force: true })
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, colorScheme: 'dark',
    recordVideo: { dir, size: { width: 1920, height: 1080 } },
  })
  const page = await ctx.newPage()
  const t0 = Date.now()
  try { await run(page) } catch (e) { console.log(`${name}: ${e.message.split('\n')[0]}`) }
  const left = seconds * 1000 - (Date.now() - t0)
  if (left > 0) await sleep(left)
  await ctx.close(); await browser.close()
  const webm = fs.readdirSync(dir).find((f) => f.endsWith('.webm'))
  execSync(`ffmpeg -y -loglevel error -i "${path.join(dir, webm)}" -r 30 -c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p -vf scale=1920:1080 -an "${target}"`)
  const d = execSync(`ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "${target}"`).toString().trim()
  console.log(`${name}: ${Number(d).toFixed(1)}s`)
}

// 1. Landing page, top to bottom.
await record('landing', 26, async (page) => {
  await page.goto(`${LIVE}/`, { waitUntil: 'networkidle' })
  await page.mouse.move(960, 540); await sleep(2600)
  for (let i = 0; i < 7; i++) { await scrollBy(page, 820); await sleep(1100) }
})

// 2. The console with all three apps LIVE (green) - the real integration.
await record('console-live', 12, async (page) => {
  await page.goto(`${LIVE}/dashboard`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(2500)
  await scrollBy(page, 260); await sleep(1800)
  await scrollBy(page, -260); await sleep(1500)
})

// 3. Chaos storm: faults absorbed, steps self-healed.
await record('chaos', 30, async (page) => {
  await page.goto(`${SIM}/dashboard`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1800)
  await page.click('button:has-text("Chaos storm")'); await sleep(600)
  await page.click('button:has-text("Run agent")')
  await page.waitForSelector('text=Chain verified', { timeout: 90000 })
  await sleep(1200)
  const step = page.locator('#execution button[aria-expanded="false"]').first()
  if (await step.count()) { await step.click(); await sleep(3200) }   // open the retry waterfall
  await scrollBy(page, 420); await sleep(2200)
})

// 4. Stripe outage: the rollback.
await record('rollback', 24, async (page) => {
  await page.goto(`${SIM}/dashboard`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)
  await page.click('button:has-text("Stripe outage")'); await sleep(600)
  await page.click('button:has-text("Run agent")')
  await page.waitForSelector('text=Chain verified', { timeout: 90000 })
  await sleep(2500)
  await scrollBy(page, 380); await sleep(2500)
})

// 5. The sealed audit chain.
await record('audit', 10, async (page) => {
  await page.goto(`${SIM}/dashboard`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)
  await page.click('button:has-text("Clean run")'); await sleep(400)
  await page.click('button:has-text("Run agent")')
  await page.waitForSelector('text=Chain verified', { timeout: 90000 })
  await page.locator('#audit').scrollIntoViewIfNeeded(); await sleep(3500)
})

console.log('capture done')
