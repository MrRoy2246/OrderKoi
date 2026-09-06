/**
 * Regenerates the raster public assets from public/favicon.svg:
 *
 *   public/favicon.ico        32×32  (PNG-in-ICO fallback for legacy browsers)
 *   public/apple-touch-icon.png 180×180 (iOS home-screen icon, full-bleed)
 *   public/og-image.png       1200×630 (social share card, brand font)
 *
 * Run from frontend/ with the dev deps installed:
 *   node scripts/generate-assets.mjs
 *
 * Uses Playwright's bundled Chromium as the renderer, so the SVG mark is
 * identical to the one in the browser tab. Commit the generated files —
 * this script only needs to run when the logo changes.
 */

import { chromium } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const frontendDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const publicDir = path.join(frontendDir, "public");
const markSvg = readFileSync(path.join(publicDir, "favicon.svg"), "utf8");

// The Manrope variable font shipped with the app (exact same file the
// site loads), so the share card matches the brand typeface.
const fontPath = path.join(
  frontendDir,
  "node_modules",
  "@fontsource-variable",
  "manrope",
  "files",
  "manrope-latin-wght-normal.woff2",
);

const brandColors = {
  ink: "#1c1917",
  text: "#44403c",
  muted: "#78716c",
  paper: "#fff4e6",
};

const pageWrap = (body, width, height) => `
  <!doctype html>
  <html>
  <head>
    <meta charset="utf-8" />
    <style>
      @font-face {
        font-family: "Manrope Variable";
        src: url("file:///${fontPath.replace(/\\/g, "/")}") format("woff2-variations");
        font-weight: 200 800;
      }
      * { margin: 0; padding: 0; }
      html, body { width: ${width}px; height: ${height}px; overflow: hidden; }
    </style>
  </head>
  <body>${body}</body>
  </html>
`;

/** The mark, full-bleed (no rounded corners — iOS rounds the icon itself). */
const fullBleedMark = markSvg
  .replace('viewBox="0 0 32 32"', 'viewBox="0 0 32 32" width="__SIZE__" height="__SIZE__"')
  .replace("<rect width=\"32\" height=\"32\" rx=\"9\"", "<rect width=\"32\" height=\"32\" rx=\"0\"");

const ogCard = `
  <div style="
    width: 1200px; height: 630px; background: ${brandColors.paper};
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 28px; font-family: 'Manrope Variable', system-ui, sans-serif;
  ">
    ${markSvg.replace("<svg ", '<svg width="150" height="150" ')}
    <div style="
      font-size: 96px; font-weight: 800; color: ${brandColors.ink}; letter-spacing: -0.02em;
    ">OrderKoi</div>
    <div style="
      font-size: 34px; font-weight: 500; color: ${brandColors.text};
    ">Order tracking for online sellers — every order, one link.</div>
    <div style="
      font-size: 24px; font-weight: 500; color: ${brandColors.muted}; margin-top: 8px;
    ">Free to start &middot; Unlimited orders on Pro</div>
  </div>
`;

/** Wrap a PNG in a single-image ICO container (Vista+ PNG-in-ICO). */
const pngToIco = (png) => {
  const header = Buffer.alloc(22);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // type: icon
  header.writeUInt16LE(1, 4); // image count
  header.writeUInt8(32, 6); // width
  header.writeUInt8(32, 7); // height
  header.writeUInt8(0, 8); // palette
  header.writeUInt8(0, 9); // reserved
  header.writeUInt16LE(1, 10); // color planes
  header.writeUInt16LE(32, 12); // bits per pixel
  header.writeUInt32LE(png.length, 14); // data size
  header.writeUInt32LE(22, 18); // data offset
  return Buffer.concat([header, png]);
};

const browser = await chromium.launch();
const render = async (html, width, height, { transparent = false } = {}) => {
  const page = await browser.newPage({
    viewport: { width, height },
    deviceScaleFactor: 1,
  });
  await page.setContent(html, { waitUntil: "networkidle" });
  const buffer = await page.screenshot({
    clip: { x: 0, y: 0, width, height },
    omitBackground: transparent,
  });
  await page.close();
  return buffer;
};

// 1. favicon.ico — rounded-rect mark on transparency, 32×32
const faviconPng = await render(
  pageWrap(markSvg.replace("<svg ", '<svg width="32" height="32" '), 32, 32),
  32,
  32,
  { transparent: true },
);
writeFileSync(path.join(publicDir, "favicon.ico"), pngToIco(faviconPng));
console.log("✓ favicon.ico (32×32)");

// 2. apple-touch-icon.png — full-bleed, 180×180
writeFileSync(
  path.join(publicDir, "apple-touch-icon.png"),
  await render(pageWrap(fullBleedMark.replace(/__SIZE__/g, "180"), 180, 180), 180, 180),
);
console.log("✓ apple-touch-icon.png (180×180)");

// 3. og-image.png — social share card, 1200×630
writeFileSync(
  path.join(publicDir, "og-image.png"),
  await render(pageWrap(ogCard, 1200, 630), 1200, 630),
);
console.log("✓ og-image.png (1200×630)");

await browser.close();
