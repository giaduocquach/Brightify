// Headless diagnostics against the running FastAPI server (:8000).
import { chromium } from 'playwright';

const BASE = process.env.BASE || 'http://127.0.0.1:8000';
const errors = [];
const apiCalls = [];

const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
page.on('response', (r) => {
  if (r.url().includes('/api/recommend/color')) apiCalls.push(`${r.status()} ${r.url()}`);
});

await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const canvasCount = await page.locator('canvas').count();
const title = await page.locator('.home-title').textContent().catch(() => null);

// Activate the accessible "Đỏ" control via keyboard (same path as orb click).
let activated = false;
try {
  const btn = page.getByRole('button', { name: /Đỏ —/ });
  await btn.focus();
  await page.keyboard.press('Enter');
  activated = true;
} catch (e) { errors.push(`activate: ${e.message}`); }

await page.waitForTimeout(6000); // allow recommend round-trip

const resultCount = await page.locator('.result-row').count().catch(() => 0);
const chipCount = await page.locator('.selected-chip').count().catch(() => 0);

// Play the first enabled result → player bar should appear.
let playerVisible = false, playerTitle = null;
try {
  await page.locator('.result-row:not([disabled])').first().click();
  await page.waitForSelector('.player', { timeout: 4000 });
  playerVisible = true;
  playerTitle = await page.locator('.player-title').textContent();
} catch { /* no playable row */ }

// Open now-playing overlay.
let npoVisible = false;
if (playerVisible) {
  try {
    await page.locator('.player-track').click();
    await page.waitForSelector('.npo', { timeout: 2000 });
    npoVisible = true;
  } catch { /* none */ }
}

console.log(JSON.stringify({
  canvasCount, title, activated,
  chipCount, resultCount,
  playerVisible, playerTitle, npoVisible,
  apiCalls,
  consoleErrors: errors.slice(0, 12),
}, null, 2));

await browser.close();
