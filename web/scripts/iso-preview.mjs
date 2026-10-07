// Preview every isometric figure, light and dark, as PNGs (development aid).
//   node scripts/iso-preview.mjs <outdir> [name-filter] [width]
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import * as F from "../src/components/iso/preview.ts";

const out = process.argv[2] ?? "iso-preview";
const only = process.argv[3] ?? "";
const width = Number(process.argv[4] ?? 1200);
mkdirSync(out, { recursive: true });
const css = readFileSync("src/styles/tokens.css", "utf8").replace(/@theme[^{]*\{[\s\S]*?\n\}/g, "") + readFileSync("src/styles/iso.css", "utf8");
const cases = Object.entries(F.PREVIEW ?? {}).filter(([k]) => k.includes(only));
const cells = cases.map(([k, fig]) => `<figure><svg class="iso is-play" viewBox="${fig.viewBox}">${fig.body}</svg><figcaption>${k}</figcaption></figure>`).join("");
const browser = await chromium.launch({ channel: "msedge", headless: true });
for (const theme of ["light", "dark"]) {
  const html = `<!doctype html><html data-theme="${theme}"><head><style>${css}
  body{margin:0;padding:16px;background:var(--bg);color:var(--text);font:12px system-ui}
  main{display:grid;grid-template-columns:repeat(auto-fill,minmax(${only ? 520 : 340}px,1fr));gap:16px}
  figure{margin:0;border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--bg)}</style></head>
  <body><main>${cells}</main></body></html>`;
  writeFileSync(`${out}/${theme}.html`, html);
  const page = await browser.newPage({ viewport: { width, height: 800 }, reducedMotion: "reduce" });
  await page.goto(pathToFileURL(resolve(out, `${theme}.html`)).href);
  await page.screenshot({ path: `${out}/${theme}.png`, fullPage: true });
}
await browser.close();
console.log("wrote", cases.length, "figures to", out);
