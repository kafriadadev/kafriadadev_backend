// Write the isometric figures as standalone SVG files.
//
//   node scripts/iso-export.mjs
//
// public/figures/iso/<name>.svg: self-contained (styles inside), light and dark
//   by the reader's system setting, for places that cannot render the figure on
//   the server (error.tsx is a client component; loading the drawing code there
//   would add it to every page's JavaScript).
// ../docs/design/print/<name>.svg: light only, for posters, flyers and banners.
//   Open in a browser or Inkscape and print or export at any size: it is vector.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { PREVIEW } from "../src/components/iso/preview.ts";

const tokens = readFileSync("src/styles/tokens.css", "utf8").replace(/@theme[^{]*\{[\s\S]*?\n\}/g, "");
const iso = readFileSync("src/styles/iso.css", "utf8");
const min = (css) => css.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\s+/g, " ").replace(/\s*([{};:,>])\s*/g, "$1").trim();
// Only the light block of each: the print files never switch.
const lightOnly = (css) => css
  .replace(/^@media \(prefers-color-scheme: dark\) \{.*\}\s*\}\s*$/gm, "")
  .replace(/@media \(prefers-color-scheme: dark\) \{\r?\n[\s\S]*?\r?\n\}\r?\n/g, "")
  .replace(/:root\[data-theme="dark"\][^{]*\{[^}]*\}/g, "");

// The site's pages: what error.tsx and friends load. Kept to the ones a client component needs.
const SITE = ["held-red", "held-yellow", "server-down", "no-signal", "out-of-play"];

function file(name, css) {
  const fig = PREVIEW[name];
  const [, , w, h] = fig.viewBox.split(" ").map(Number);
  return `<svg xmlns="http://www.w3.org/2000/svg" class="iso" viewBox="${fig.viewBox}" width="${Math.round(w * 3)}" height="${Math.round(h * 3)}"><style>${css}</style>${fig.body}</svg>\n`;
}

mkdirSync("public/figures/iso", { recursive: true });
const siteCss = min(tokens + iso);
for (const name of SITE) writeFileSync(`public/figures/iso/${name}.svg`, file(name, siteCss));

mkdirSync("../docs/design/print", { recursive: true });
const printCss = min(lightOnly(tokens) + lightOnly(iso));
for (const name of Object.keys(PREVIEW)) writeFileSync(`../docs/design/print/${name}.svg`, file(name, printCss));
console.log(`wrote ${SITE.length} site figures and ${Object.keys(PREVIEW).length} print figures`);
