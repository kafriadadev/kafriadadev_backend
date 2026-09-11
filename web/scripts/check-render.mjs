/**
 * What the pages actually look like in a browser — measured, not reasoned about.
 *
 *   npm run check:render
 *
 * Needs both tiers running (bash scripts/dev.sh). Drives the Microsoft Edge that
 * is already installed through playwright-core, so there is no browser download.
 *
 * WHY THIS EXISTS
 * The document's colours were "fixed" twice by reading code, and were wrong
 * both times: first the ink followed the theme while the paper did not, then
 * inline styles in the TSX overrode the CSS fix. Grep cannot see a computed
 * colour. A browser can. So this measures, for every visible piece of text, the
 * contrast between the colour it is drawn in and the colour it is drawn on.
 *
 * It checks, at a real 360px phone viewport, in both light and dark:
 *   1. WCAG contrast of every text element (4.5:1, or 3:1 for large text)
 *   2. that nothing extends past the right edge of the screen
 *   3. that registration works with JavaScript switched OFF
 *
 * Exit code is non-zero if anything fails, so it can gate a commit.
 */

import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright-core";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const KUID = process.env.KUID ?? "KA-NG-JG-BKD-2026-000115";
const SIG = process.env.SIG ?? "";
const OUT = process.env.SHOT_DIR; // optional: where to save full-page screenshots

const PAGES = [
  ["home", "/"],
  ["register", "/register"],
  ["find", "/find"],
  ["privacy", "/privacy"],
  ["profile", `/a/${KUID}${SIG ? `?s=${SIG}` : ""}`],
  ["card", `/card/${KUID}`],
];

// 360 x 780 is the most common viewport among cheap Android handsets.
const PHONE = { width: 360, height: 780 };

/** Runs inside the page. Returns overflow offenders and contrast failures. */
function audit() {
  const vw = window.innerWidth;

  const parse = (c) => {
    let m = c.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    if (m) return [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]];
    m = c.match(/color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\)/);
    if (m) return [m[1] * 255, m[2] * 255, m[3] * 255, m[4] === undefined ? 1 : +m[4]];
    return null;
  };
  const over = (top, under) => {
    const a = top[3];
    return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat(1);
  };
  const lum = ([r, g, b]) => {
    const f = (v) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (a, b) => {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };
  // The colour actually painted behind an element: every translucent layer
  // between it and the root, composited from the bottom up.
  const backdrop = (el) => {
    const layers = [];
    for (let n = el; n; n = n.parentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c[3] > 0) {
        layers.push(c);
        if (c[3] === 1) break;
      }
    }
    let acc = [255, 255, 255, 1];
    for (const layer of layers.reverse()) acc = over(layer, acc);
    return acc;
  };
  const hex = (c) => "#" + c.slice(0, 3).map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");

  const overflow = [];
  const contrast = [];
  let checked = 0;

  for (const el of document.body.querySelectorAll("*")) {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") continue;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;

    // Past the right edge. overflow-x:hidden on <body> would hide this from the
    // scrollbar, which is exactly why it has to be measured per element.
    if (rect.right > vw + 1 && !el.closest(".skip-link")) {
      overflow.push(`${el.tagName.toLowerCase()}${el.className && typeof el.className === "string" ? "." + el.className.trim().replace(/\s+/g, ".") : ""} right=${Math.round(rect.right)}px`);
    }

    if (el.tagName === "OPTION" || el.closest(".skip-link")) continue;
    const text = [...el.childNodes]
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent.trim())
      .join(" ")
      .trim();
    if (!text) continue;

    const fg = parse(cs.color);
    if (!fg) continue;
    const bg = backdrop(el);
    const r = ratio(over(fg, bg), bg);
    const size = parseFloat(cs.fontSize);
    const large = size >= 24 || (size >= 18.66 && +cs.fontWeight >= 700);
    const need = large ? 3 : 4.5;
    checked++;
    if (r < need) {
      contrast.push(`${r.toFixed(2)}:1 (need ${need})  ${hex(fg)} on ${hex(bg)}  <${el.tagName.toLowerCase()}> "${text.slice(0, 48)}"`);
    }
  }
  // An identifier may wrap only after a hyphen. Splitting "000115" as
  // "0001 / 15" is how an ID gets copied onto paper wrong, and it looks fine to
  // every other check here.
  const splits = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent;
    const at = text.search(/KA-[A-Z]{2}-[A-Z]{2}-[A-Z]{3}-\d{4}-\d{6}/);
    if (at < 0 || !node.parentElement?.getClientRects().length) continue;
    const range = document.createRange();
    let lastTop = null;
    for (let i = at; i < at + 24; i++) {
      range.setStart(node, i);
      range.setEnd(node, i + 1);
      const r = range.getClientRects()[0];
      if (!r) continue;
      if (lastTop !== null && r.top > lastTop + 2 && text[i - 1] !== "-") {
        splits.push(`"${text.slice(at, i)} / ${text.slice(i, at + 24)}"`);
      }
      lastTop = r.top;
    }
  }
  return { overflow: [...new Set(overflow)].slice(0, 10), contrast, splits, checked };
}

const browser = await chromium.launch({ channel: "msedge", headless: true });
let failures = 0;

try {
  // 320px is the narrowest screen the pilot designs for; one pass there is
  // enough to catch what only breaks when space runs out.
  const RUNS = [["light", PHONE.width], ["dark", PHONE.width], ["dark", 320]];
  for (const [scheme, width] of RUNS) {
    const ctx = await browser.newContext({
      viewport: { width, height: PHONE.height },
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true,
      colorScheme: scheme,
    });
    const page = await ctx.newPage();
    console.log(`\n=== ${scheme.toUpperCase()} · ${width}px ===`);

    for (const [name, path] of PAGES) {
      const res = await page.goto(BASE + path, { waitUntil: "load", timeout: 90_000 });
      const status = res?.status() ?? 0;
      const { overflow, contrast, splits, checked } = await page.evaluate(audit);
      const ok = status === 200 && !overflow.length && !contrast.length && !splits.length;
      if (!ok) failures++;
      console.log(`${ok ? "  ok  " : "  FAIL"}  ${name.padEnd(9)} HTTP ${status}  ${checked} text elements, ${contrast.length} low-contrast, ${overflow.length} overflowing, ${splits.length} split IDs`);
      for (const line of contrast) console.log(`          contrast  ${line}`);
      for (const line of overflow) console.log(`          overflow  ${line}`);
      for (const line of splits) console.log(`          split ID  ${line}`);

      if (OUT && (name === "card" || name === "profile" || name === "register")) {
        mkdirSync(OUT, { recursive: true });
        await page.screenshot({ path: join(OUT, `${name}-${scheme}-${width}.png`), fullPage: true });
      }
    }
    await ctx.close();
  }

  // -- Registration with JavaScript OFF --------------------------------------
  // Submitted deliberately without the privacy notice ticked. That is rejected
  // by the web tier before the API is called, so the test proves the whole
  // no-JS POST -> redirect -> re-render loop while writing nothing anywhere.
  console.log("\n=== REGISTRATION WITH JAVASCRIPT OFF ===");
  const ctx = await browser.newContext({ viewport: PHONE, isMobile: true, javaScriptEnabled: false });
  const page = await ctx.newPage();
  await page.goto(BASE + "/register", { waitUntil: "load", timeout: 90_000 });
  const secret = "correct horse battery staple";
  await page.fill("#full_name", "No Script Tester");
  await page.fill("#phone", "0803 000 0000");
  await page.fill("#date_of_birth", "1998-03-14");
  const firstOpen = await page.$eval("#lga_id optgroup:first-of-type option", (o) => o.value);
  await page.selectOption("#lga_id", firstOpen);
  await page.fill("#password", secret);
  await Promise.all([page.waitForLoadState("load"), page.click("button[type=submit]")]);
  await page.waitForURL(/\/register\?/, { timeout: 60_000 });

  const url = new URL(page.url());
  const checks = [
    ["form posted and came back without any script", url.pathname === "/register"],
    ["the rejection names the consent box", url.searchParams.get("field") === "accept_privacy_notice"],
    ["the message is shown on the page", (await page.locator("[role=alert]").count()) > 0],
    ["typed name survives the round trip", (await page.inputValue("#full_name")) === "No Script Tester"],
    ["chosen LGA survives the round trip", (await page.inputValue("#lga_id")) === firstOpen],
    ["password is NOT in the URL", !page.url().includes(encodeURIComponent(secret)) && !page.url().includes(secret)],
    ["password box comes back empty", (await page.inputValue("#password")) === ""],
  ];
  for (const [label, pass] of checks) {
    if (!pass) failures++;
    console.log(`${pass ? "  ok  " : "  FAIL"}  ${label}`);
  }
  await ctx.close();
} finally {
  await browser.close();
}

console.log(failures ? `\n${failures} FAILED` : "\nall passed");
process.exit(failures ? 1 : 0);
