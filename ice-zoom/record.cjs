/**
 * Renders ice-zoom/index.html into video frames.
 *
 * Usage:
 *   NODE_PATH=/opt/node22/lib/node_modules node record.cjs <outDir> [fps]
 *
 * Drives the page's record mode (?record) deterministically: holds on each
 * of the 9 levels, then eases through the transition to the next, writing
 * one screenshot per output frame. Encode afterwards with ffmpeg, e.g.:
 *   ffmpeg -framerate 30 -i frame_%05d.jpg -c:v libx264 -pix_fmt yuv420p out.mp4
 */
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

const OUT = process.argv[2] || 'frames-out';
const FPS = +(process.argv[3] || 30);
const W = 1920, H = 910;

const HOLD = 2.1;    // seconds resting on each level
const TRANS = 2.6;   // seconds easing between levels
const LEVELS = 9;

const easeInOutCubic = u => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);

/* piecewise zoom position for a given time */
function zAt(t) {
  let acc = 0;
  for (let i = 0; i < LEVELS; i++) {
    if (t < acc + HOLD) return i;
    acc += HOLD;
    if (i === LEVELS - 1) return i;
    if (t < acc + TRANS) return i + easeInOutCubic((t - acc) / TRANS);
    acc += TRANS;
  }
  return LEVELS - 1;
}

const TOTAL = LEVELS * HOLD + (LEVELS - 1) * TRANS;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    executablePath: process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium',
  });
  const page = await browser.newPage({
    viewport: { width: W, height: H },
    deviceScaleFactor: 1,
  });
  const url = 'file://' + path.resolve(__dirname, 'index.html') + '?record';
  await page.goto(url);
  await page.waitForFunction('typeof window.__seek === "function"');

  const frames = Math.ceil(TOTAL * FPS);
  console.log(`rendering ${frames} frames (${TOTAL.toFixed(1)}s @ ${FPS}fps)`);
  const start = Date.now();
  for (let i = 0; i < frames; i++) {
    const t = i / FPS;
    await page.evaluate(([zv, tt]) => window.__seek(zv, tt), [zAt(t), t]);
    await page.screenshot({
      path: path.join(OUT, `frame_${String(i).padStart(5, '0')}.jpg`),
      type: 'jpeg', quality: 92,
    });
    if (i % 100 === 0) {
      const rate = (i + 1) / ((Date.now() - start) / 1000);
      console.log(`  frame ${i}/${frames}  (${rate.toFixed(1)} fps capture)`);
    }
  }
  await browser.close();
  console.log('done:', OUT);
})();
