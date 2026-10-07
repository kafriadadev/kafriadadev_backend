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
 *   3. that registration and sign-in work with JavaScript switched OFF
 *
 * With SIGNIN_PHONE and SIGNIN_PASSWORD set to a real account, it also signs in
 * with JavaScript off, audits the signed-in page, and signs out again. Without
 * them that part is skipped and says so.
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
const SIGNIN_PHONE = process.env.SIGNIN_PHONE;
const SIGNIN_PASSWORD = process.env.SIGNIN_PASSWORD;

const PAGES = [
  ["home", "/"],
  ["register", "/register"],
  ["club-signup", "/clubs/register"],
  ["sign-in", "/sign-in"],
  ["forgot", "/forgot"],
  ["find", "/find"],
  ["privacy", "/privacy"],
  ["profile", `/a/${KUID}${SIG ? `?s=${SIG}` : ""}`],
  ["card", `/card/${KUID}`],
  // Served only when the web tier runs with STYLEGUIDE=1 (or in development).
  ...(process.env.STYLEGUIDE ? [["styleguide", "/styleguide"], ["components", "/styleguide/components"]] : []),
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

  // Content cut off by an ancestor that clips (an SVG, overflow:hidden, a
  // scrolling strip) and that itself fits on screen is not visible overflow.
  const clippedInside = (el) => {
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const ox = getComputedStyle(a).overflowX;
      const clips = ox !== "visible" || a.tagName.toLowerCase() === "svg";
      if (clips && a.getBoundingClientRect().right <= vw + 1) return true;
    }
    return false;
  };
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
    if (rect.right > vw + 1 && !el.closest(".skip-link") && !clippedInside(el)) {
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
      // A break after a dash counts too: "KA-NG-JG-BKD- / 2026-001569" is copied
      // down as two things.
      if (lastTop !== null && r.top > lastTop + 2) {
        splits.push(`"${text.slice(at, i)} / ${text.slice(i, at + 24)}"`);
      }
      lastTop = r.top;
    }
  }
  return { overflow: [...new Set(overflow)].slice(0, 10), contrast, splits, checked };
}

const browser = await chromium.launch({ channel: "msedge", headless: true });
let failures = 0;

/** Audit the page that is loaded and print one line for it. */
async function report(page, name, status, shotSuffix) {
  const { overflow, contrast, splits, checked } = await page.evaluate(audit);
  const ok = status === 200 && !overflow.length && !contrast.length && !splits.length;
  if (!ok) failures++;
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${name.padEnd(9)} HTTP ${status}  ${checked} text elements, ${contrast.length} low-contrast, ${overflow.length} overflowing, ${splits.length} split IDs`);
  for (const line of contrast) console.log(`          contrast  ${line}`);
  for (const line of overflow) console.log(`          overflow  ${line}`);
  for (const line of splits) console.log(`          split ID  ${line}`);
  if (OUT && ["card", "profile", "register", "sign-in", "me", "confirm", "forgot"].includes(name)) {
    mkdirSync(OUT, { recursive: true });
    await page.screenshot({ path: join(OUT, `${name}-${shotSuffix}.png`), fullPage: true });
  }
}

function check(label, pass) {
  if (!pass) failures++;
  console.log(`${pass ? "  ok  " : "  FAIL"}  ${label}`);
}

try {
  // 320px is the narrowest screen the pilot designs for; one pass there is
  // enough to catch what only breaks when space runs out.
  // 414 is a large phone; 768, 1024, 1280 and 1440 cover the tablet and desktop
  // layouts at each breakpoint and either side of them: the inline header, the
  // administrator sidebar, tables shown as tables rather than stacked cards.
  const RUNS = [
    ["light", PHONE.width], ["dark", PHONE.width], ["dark", 320], ["light", 414],
    ["light", 768], ["dark", 1024], ["dark", 1280], ["light", 1440],
  ];
  for (const [scheme, width] of RUNS) {
    const mobile = width < 700;
    const ctx = await browser.newContext({
      viewport: { width, height: mobile ? PHONE.height : 900 },
      deviceScaleFactor: mobile ? 2 : 1,
      isMobile: mobile,
      hasTouch: mobile,
      colorScheme: scheme,
    });
    const page = await ctx.newPage();
    console.log(`\n=== ${scheme.toUpperCase()} · ${width}px ===`);

    for (const [name, path] of PAGES) {
      const res = await page.goto(BASE + path, { waitUntil: "load", timeout: 90_000 });
      await report(page, name, res?.status() ?? 0, `${scheme}-${width}`);
    }
    await ctx.close();
  }

  // -- Public page budget ------------------------------------------------------
  // The pages a stranger lands on, often on one bar of signal. The design plan's
  // launch budget is 150 KB first load with at most 50 KB of JavaScript; the
  // public profile a scanned card opens is held to 60 KB and none. All five ship
  // no framework: registration may load one script, /enhance.js (phone grouping
  // and the busy button), the landing page /delight.js (hairline figures, which do
  // nothing on a phone), and nothing else may. Counted as transferred
  // (compressed) bytes, fresh cache, JavaScript ON, so a script that would load
  // is caught rather than skipped.
  {
    const BUDGET = [
      ["PUB-01", `/a/${KUID}${SIG ? `?s=${SIG}` : ""}`, [], 60],
      ["PUB-02", "/", ["/delight.js"], 150],
      ["PUB-03", "/find", [], 150],
      ["AUT-04", "/sign-in", [], 150],
      ["AUT-01", "/register", ["/enhance.js"], 150],
    ];
    console.log("\n=== PUBLIC PAGE BUDGET ===");
    for (const [name, path, allowed, limitKb] of BUDGET) {
      const ctx = await browser.newContext({ viewport: PHONE, isMobile: true });
      const page = await ctx.newPage();
      const loaded = [];
      page.on("requestfinished", async (req) => {
        const sizes = await req.sizes().catch(() => null);
        loaded.push({ url: req.url(), type: req.resourceType(), bytes: sizes ? sizes.responseBodySize + sizes.responseHeadersSize : 0 });
      });
      await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 90_000 });
      const external = await page.locator("script[src]").evaluateAll((els) => els.map((e) => new URL(e.src).pathname));
      const inline = await page.locator("script:not([src]):not([type='application/ld+json'])").count();
      const stray = external.filter((src) => !allowed.includes(src));
      const scriptLoads = loaded.filter((r) => r.type === "script" && !allowed.includes(new URL(r.url).pathname));
      const total = loaded.reduce((n, r) => n + r.bytes, 0);
      const js = loaded.filter((r) => r.type === "script").reduce((n, r) => n + r.bytes, 0);
      console.log(`  ${name} ${path}`);
      for (const r of loaded) console.log(`          ${String(Math.round(r.bytes / 102.4) / 10).padStart(6)} KB  ${r.type.padEnd(10)} ${r.url.replace(BASE, "")}`);
      check(`${name} ships no framework JavaScript (${external.length} external, ${inline} inline scripts)`, stray.length === 0 && inline === 0 && scriptLoads.length === 0);
      check(`${name} first load is under ${limitKb} KB (${(total / 1024).toFixed(1)} KB, ${(js / 1024).toFixed(1)} KB script)`, total < limitKb * 1024 && js <= 50 * 1024);
      await ctx.close();
    }
  }

  // -- Phone number grouping as you type (JavaScript ON) ----------------------
  {
    const ctx = await browser.newContext({ viewport: PHONE, isMobile: true });
    const page = await ctx.newPage();
    console.log("\n=== PHONE FORMATTING, JavaScript ON ===");
    // The registration form's phone field (sign-in takes a phone or an email, unformatted).
    await page.goto(BASE + "/register", { waitUntil: "networkidle", timeout: 90_000 });
    const phone = page.locator("#phone");
    await phone.pressSequentially("08031234567", { delay: 20 });
    const typed = await phone.inputValue();
    check(`typing 08031234567 shows "0803 123 4567" (${typed})`, typed === "0803 123 4567");
    // A digit typed in the middle lands where the caret was, not at the end.
    await phone.evaluate((el) => el.setSelectionRange(6, 6)); // after "0803 1"
    await page.keyboard.type("9");
    const edited = await phone.inputValue();
    const caret = await phone.evaluate((el) => el.selectionStart);
    check(`a digit inserted mid-number keeps the caret (${edited}, caret ${caret})`, edited === "0803 192 34567" && caret === 7);
    await ctx.close();
  }

  // -- Navigation with JavaScript OFF -----------------------------------------
  // On a phone the links live in a <details> sheet: the browser opens it, no
  // script involved.
  {
    const ctx = await browser.newContext({ viewport: PHONE, javaScriptEnabled: false, isMobile: true });
    const page = await ctx.newPage();
    console.log("\n=== NAVIGATION, JavaScript OFF ===");
    await page.goto(BASE + "/privacy", { waitUntil: "load", timeout: 90_000 });
    const menu = page.locator("header details");
    const hidden = !(await menu.locator("a[href='/me']").isVisible());
    await menu.locator("summary").click();
    const shown = await menu.locator("a[href='/me']").isVisible();
    await menu.locator("summary").click();
    const closed = !(await menu.locator("a[href='/me']").isVisible());
    check("the phone menu is closed on arrival, opens and closes without any script", hidden && shown && closed);
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
  await page.fill("#first_name", "Noscript");
  await page.fill("#surname", "Tester");
  await page.fill("#address_line", "4 Kano Road");
  await page.fill("#height_cm", "180");
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
    ["typed name survives the round trip", (await page.inputValue("#first_name")) === "Noscript"
      && (await page.inputValue("#surname")) === "Tester"],
    ["typed address and height survive", (await page.inputValue("#address_line")) === "4 Kano Road"
      && (await page.inputValue("#height_cm")) === "180"],
    ["chosen LGA survives the round trip", (await page.inputValue("#lga_id")) === firstOpen],
    ["password is NOT in the URL", !page.url().includes(encodeURIComponent(secret)) && !page.url().includes(secret)],
    ["password box comes back empty", (await page.inputValue("#password")) === ""],
  ];
  for (const [label, pass] of checks) check(label, pass);
  await ctx.close();

  // -- The confirm screen (AUT-02) -------------------------------------------
  // Rendered from a pending-registration cookie, which is all that screen needs
  // when nobody is signed in. Nothing is written.
  console.log("\n=== CONFIRM YOUR EMAIL ===");
  for (const [scheme, width] of [["light", PHONE.width], ["dark", 320]]) {
    const ctx = await browser.newContext({
      viewport: { width, height: PHONE.height }, isMobile: true, colorScheme: scheme,
    });
    await ctx.addCookies([{
      name: "kaf_pending",
      value: JSON.stringify({ phone: "+2349000000000", kuid: "", email: "n***@example.test" }),
      domain: "localhost", path: "/", httpOnly: true, sameSite: "Lax",
    }]);
    const page = await ctx.newPage();
    const res = await page.goto(BASE + "/register/confirm", { waitUntil: "load", timeout: 90_000 });
    check(`${scheme}: the confirm screen renders for a pending registration`,
      new URL(page.url()).pathname === "/register/confirm");
    await report(page, "confirm", res?.status() ?? 0, `${scheme}-${width}`);
    await ctx.close();
  }

  // -- Password reset with JavaScript OFF ------------------------------------
  // An unregistered number: the API answers exactly as it would for a real one
  // and writes nothing, which is the property being checked.
  console.log("\n=== PASSWORD RESET WITH JAVASCRIPT OFF ===");
  {
    const ctx = await browser.newContext({ viewport: PHONE, isMobile: true, javaScriptEnabled: false });
    const page = await ctx.newPage();
    await page.goto(BASE + "/forgot", { waitUntil: "load", timeout: 90_000 });
    await page.fill("#phone", "0900 000 0000");
    await Promise.all([page.waitForLoadState("load"), page.click("button[type=submit]")]);
    await page.waitForURL(/\/forgot\?/, { timeout: 60_000 });
    check("an unknown number is told a code is on its way, like any other",
      (await page.locator("[role=status]").count()) > 0);

    const secret = "a brand new passphrase";
    await page.fill("#code", "000000");
    await page.fill("#new_password", secret);
    await Promise.all([page.waitForLoadState("load"), page.click("button[type=submit]")]);
    await page.waitForURL(/\/forgot\?/, { timeout: 60_000 });
    check("a wrong code is refused on the page", (await page.locator("[role=alert]").count()) > 0);
    check("the new password is NOT in the URL", !page.url().includes(encodeURIComponent(secret)));
    await ctx.close();
  }

  // -- Sign-in with JavaScript OFF, wrong credentials -------------------------
  // A number in a range no subscriber holds, so the API finds no account and
  // writes nothing — and answers exactly as it would for a wrong password.
  console.log("\n=== SIGN-IN WITH JAVASCRIPT OFF ===");
  {
    const ctx = await browser.newContext({ viewport: PHONE, isMobile: true, javaScriptEnabled: false });
    const page = await ctx.newPage();
    await page.goto(BASE + "/sign-in", { waitUntil: "load", timeout: 90_000 });
    const guess = "not the right password";
    await page.fill("#phone", "0900 000 0000");
    await page.fill("#password", guess);
    await Promise.all([page.waitForLoadState("load"), page.click("button[type=submit]")]);
    await page.waitForURL(/\/sign-in\?/, { timeout: 60_000 });
    const alert = (await page.locator("[role=alert]").textContent()) ?? "";
    check("form posted and came back without any script", new URL(page.url()).pathname === "/sign-in");
    check("one message that does not say which half was wrong", alert.includes("phone number and password do not match"));
    check("typed phone survives the round trip", (await page.inputValue("#phone")) === "0900 000 0000");
    check("password is NOT in the URL", !page.url().includes(encodeURIComponent(guess)) && !page.url().includes(guess));
    check("no session cookie was set", !(await ctx.cookies()).some((c) => c.name === "kaf_session"));
    await ctx.close();
  }

  // -- A real sign-in, the signed-in page, and sign-out -----------------------
  if (SIGNIN_PHONE && SIGNIN_PASSWORD) {
    console.log("\n=== SIGNED IN, JAVASCRIPT OFF ===");
    for (const [scheme, width] of [["light", PHONE.width], ["dark", 320]]) {
      const ctx = await browser.newContext({
        viewport: { width, height: PHONE.height }, isMobile: true,
        javaScriptEnabled: false, colorScheme: scheme,
      });
      const page = await ctx.newPage();
      await page.goto(BASE + "/sign-in", { waitUntil: "load", timeout: 90_000 });
      await page.fill("#phone", SIGNIN_PHONE);
      await page.fill("#password", SIGNIN_PASSWORD);
      await Promise.all([page.waitForLoadState("load"), page.click("button[type=submit]")]);
      await page.waitForURL(/\/me$/, { timeout: 60_000 });
      const cookie = (await ctx.cookies()).find((c) => c.name === "kaf_session");
      check(`${scheme}: signed in and landed on /me`, new URL(page.url()).pathname === "/me");
      check(`${scheme}: session cookie is httpOnly and SameSite=Lax`, !!cookie && cookie.httpOnly && cookie.sameSite === "Lax");
      await report(page, "me", 200, `${scheme}-${width}`);

      // The athlete screens (ATH-02/04/05, VER-01 to 05, VER-03). Looked at, never
      // submitted: submitting creates a payment, a file or an edit.
      for (const [name, path] of [["pay", "/pay"], ["verify", "/verify"], ["payments", "/payments"], ["clubs", "/clubs"], ["details", "/details"]]) {
        await page.goto(BASE + path, { waitUntil: "load", timeout: 90_000 });
        await report(page, name, 200, `${scheme}-${width}`);
      }
      await page.goto(BASE + "/me", { waitUntil: "load", timeout: 90_000 });

      await Promise.all([page.waitForLoadState("load"), page.click("button[type=submit]")]);
      await page.waitForURL((u) => u.pathname === "/", { timeout: 60_000 });
      check(`${scheme}: signed out, cookie gone`, !(await ctx.cookies()).some((c) => c.name === "kaf_session"));
      await page.goto(BASE + "/me", { waitUntil: "load", timeout: 90_000 });
      check(`${scheme}: /me now sends you to sign in`, new URL(page.url()).pathname === "/sign-in");
      await ctx.close();
    }
  } else {
    console.log("\n  skip  signed-in checks (set SIGNIN_PHONE and SIGNIN_PASSWORD to run them)");
  }

  // -- Other people's screens, by session token -------------------------------------
  // Screens that only exist in a certain state (under review, rejected, a reviewer's
  // queue) cannot be reached by signing in as one throwaway athlete. Hand this a list
  // of sessions already in those states and it audits each page they name.
  //   EXTRA_SESSIONS='[{"token":"...","paths":["/verify"]}]'
  if (process.env.EXTRA_SESSIONS) {
    console.log("\n=== SCREENS THAT DEPEND ON STATE ===");
    for (const [scheme, width] of [["light", PHONE.width], ["dark", 320], ["light", 414], ["light", 768], ["dark", 1024], ["dark", 1280], ["light", 1440]]) {
      console.log(`  -- ${scheme} · ${width}px`);
      for (const { token, paths } of JSON.parse(process.env.EXTRA_SESSIONS)) {
        const mobile = width < 700;
        const ctx = await browser.newContext({
          viewport: { width, height: mobile ? PHONE.height : 900 }, isMobile: mobile,
          javaScriptEnabled: false, colorScheme: scheme,
        });
        await ctx.addCookies([{ name: "kaf_session", value: token, url: BASE }]);
        const page = await ctx.newPage();
        for (const path of paths) {
          const res = await page.goto(BASE + path, { waitUntil: "load", timeout: 90_000 });
          await report(page, path.split("?")[0].replace(/[^a-z/]/gi, "").slice(0, 24) || "page", res?.status() ?? 0, `${scheme}-${width}`);
        }
        await ctx.close();
      }
    }
  }
} finally {
  await browser.close();
}

console.log(failures ? `\n${failures} FAILED` : "\nall passed");
process.exit(failures ? 1 : 0);
