// Accessibility gate: axe-core (WCAG 2.2 A and AA rules) on every listed page,
// at 320px and 1280px, light and dark, in the installed Edge.
//
//   node scripts/check-a11y.mjs            (web tier on BASE_URL, default :3000)
//   STYLEGUIDE=1 node scripts/check-a11y.mjs   also audits /styleguide pages
//
// Exits 1 on any violation. Runs with JavaScript on: axe is a script.
import { chromium } from "playwright-core";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const AXE = require.resolve("axe-core/axe.min.js");
const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const KUID = process.env.KUID ?? "KA-NG-JG-BKD-2026-000115"; // same record check-render uses

const PAGES = [
  "/", "/register", "/clubs/register", "/sign-in", "/forgot", "/find", "/privacy",
  `/a/${KUID}`, `/card/${KUID}`,
  ...(process.env.STYLEGUIDE ? ["/styleguide", "/styleguide/components"] : []),
];
const VIEWS = [
  { width: 320, scheme: "light" }, { width: 320, scheme: "dark" },
  { width: 1280, scheme: "light" }, { width: 1280, scheme: "dark" },
];

// With SIGNIN_PHONE and SIGNIN_PASSWORD, the athlete screens are audited too.
const SIGNED_IN = process.env.SIGNIN_PHONE && process.env.SIGNIN_PASSWORD
  ? ["/me", "/verify", "/pay", "/payments", "/clubs", "/details"] : [];

// EXTRA_SESSIONS='[{"token":"...","paths":["/clubs/<id>"]}]': audit more paths
// with that session (the same shape check-render.mjs takes). One session per run.
const EXTRA = JSON.parse(process.env.EXTRA_SESSIONS ?? "[]");

const browser = await chromium.launch({ channel: "msedge" });
let failures = 0;
for (const v of VIEWS) {
  const ctx = await browser.newContext({ viewport: { width: v.width, height: 800 }, colorScheme: v.scheme, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  if (SIGNED_IN.length) {
    await page.goto(BASE + "/sign-in", { waitUntil: "networkidle" });
    await page.locator("#phone").pressSequentially(process.env.SIGNIN_PHONE);
    await page.fill("#password", process.env.SIGNIN_PASSWORD);
    await Promise.all([page.waitForURL(/\/me/, { timeout: 60_000 }), page.click("form button[type=submit]")]);
  }
  for (const extra of EXTRA) await ctx.addCookies([{ name: "kaf_session", value: extra.token, url: BASE }]);
  for (const path of [...PAGES, ...SIGNED_IN, ...EXTRA.flatMap((e) => e.paths)]) {
    const res = await page.goto(BASE + path, { waitUntil: "load", timeout: 90_000 });
    await page.addScriptTag({ path: AXE });
    const result = await page.evaluate(async () =>
      // eslint-disable-next-line no-undef
      axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] } }),
    );
    const bad = result.violations;
    const tag = `${v.scheme}-${v.width}`.padEnd(10);
    console.log(`${bad.length ? "  FAIL" : "  ok  "}  ${tag} ${path.padEnd(30)} HTTP ${res?.status()}  ${bad.length} violations`);
    for (const x of bad) {
      failures++;
      console.log(`          ${x.id} (${x.impact}): ${x.help}`);
      for (const n of x.nodes.slice(0, 3)) console.log(`            ${n.target.join(" ")}  ${n.failureSummary?.split("\n")[1]?.trim() ?? ""}`);
    }
  }
  await ctx.close();
}
await browser.close();
console.log(failures ? `\n${failures} violation(s)` : "\nno violations");
process.exit(failures ? 1 : 0);
