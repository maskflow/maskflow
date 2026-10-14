// Render the animated demo SVG to PNG frames with the user's Chrome, by
// pausing every CSS animation and seeking it to each frame's time.
// usage: node record.mjs <deps-dir> <svg> <frames-dir> <seconds> <fps> <anim-seconds> <rate>
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const [depsDir, svgPath, framesDir, seconds, fps, animSeconds, rate] = process.argv.slice(2);
const require = createRequire(depsDir + "/package.json");
const puppeteer = require("puppeteer-core");

const svg = readFileSync(svgPath, "utf8");
const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
  args: ["--hide-scrollbars"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1.5 }); // 1920x1080
await page.setContent(
  `<!doctype html><html><body style="margin:0;background:#0d1117">${svg}</body></html>`,
  { waitUntil: "load" },
);

const total = Number(seconds) * Number(fps);
for (let i = 0; i < total; i++) {
  // Play the animation at `rate` x speed up to `animSeconds`, then hold.
  const videoTime = (i / Number(fps)) * Number(rate);
  const t = Math.min(videoTime, Number(animSeconds)) * 1000;
  await page.evaluate((ms) => {
    for (const a of document.getAnimations()) {
      a.pause();
      a.currentTime = ms;
    }
  }, t);
  await page.screenshot({ path: `${framesDir}/f${String(i).padStart(5, "0")}.png` });
}
await browser.close();
console.log(`${total} frames`);
