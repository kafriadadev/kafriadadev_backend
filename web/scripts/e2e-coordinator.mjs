// The coordinator's day, JavaScript OFF, counting taps: CRD-01, CRD-02 (reject,
// then approve after the athlete resubmits), CRD-03 and CRD-04.
//
//   COORD_PHONE=... ATHLETE_PHONE=... CASH_KUID=... node scripts/e2e-coordinator.mjs
//
// COORD_PHONE: an lga_coordinator for the athlete's LGA (scripts/dev_staff.py makes
// one, password "a long staff phrase 42"). ATHLETE_PHONE: an athlete under review
// in that LGA (e2e-register + e2e-verify, password "a long test phrase 42").
// CASH_KUID: an unverified athlete in the LGA with both files added, for the cash
// route. WRITES decisions to the dev database.
import { chromium } from "playwright-core";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const STAFF_PASSWORD = process.env.COORD_PASSWORD ?? "a long staff phrase 42";
const ATHLETE_PASSWORD = "a long test phrase 42";
const { COORD_PHONE, ATHLETE_PHONE, CASH_KUID } = process.env;
if (!COORD_PHONE || !ATHLETE_PHONE) throw new Error("Set COORD_PHONE and ATHLETE_PHONE (see the header).");

let failed = 0;
const check = (label, ok) => {
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${label}`);
  if (!ok) failed++;
};
const text = async (p) => (await p.locator("main").innerText()).toLowerCase();

const browser = await chromium.launch({ channel: "msedge" });
const open = async (phone, password, viewport) => {
  const ctx = await browser.newContext({ viewport, javaScriptEnabled: false });
  // Generous: a coordinator screen makes several API calls, and the dev database link varies.
  ctx.setDefaultTimeout(120_000);
  ctx.setDefaultNavigationTimeout(120_000);
  const p = await ctx.newPage();
  await p.goto(`${BASE}/sign-in`, { waitUntil: "load" });
  await p.fill("#phone", phone);
  await p.fill("#password", password);
  await Promise.all([p.waitForLoadState("load"), p.click("form button[type=submit]")]);
  return p;
};
// A coordinator on a 768px tablet; the athlete on a 360px phone.
const coord = await open(COORD_PHONE, STAFF_PASSWORD, { width: 768, height: 1024 });
const athlete = await open(ATHLETE_PHONE, ATHLETE_PASSWORD, { width: 360, height: 780 });
await athlete.goto(`${BASE}/me`, { waitUntil: "load" });
const kuid = (await athlete.locator("main").innerText()).match(/KA-NG-[A-Z]{2}-[A-Z]{3}-\d{4}-\d{6}/)?.[0];

// -- CRD-01 ---------------------------------------------------------------------
await coord.goto(`${BASE}/coordinator`, { waitUntil: "load" });
const today = await text(coord);
check("CRD-01 shows the LGA's scoreboard", today.includes("registered") && today.includes("to review"));
check("CRD-01 pins today's cash total", today.includes("cash today"));

/**
 * Find this athlete's case. The queue is oldest first and a fresh case is near
 * the end, so read the total from the first case and walk back from the last.
 */
const findCase = async () => {
  await coord.goto(`${BASE}/review?n=0`, { waitUntil: "load" });
  const first = await coord.locator("main").innerText();
  if (first.includes(kuid)) return coord.url();
  const total = Number(first.match(/case \d+ of (\d+)/i)?.[1] ?? 0);
  for (let n = total - 1; n > 0; n--) {
    await coord.goto(`${BASE}/review?n=${n}`, { waitUntil: "load" });
    if ((await coord.locator("main").innerText()).includes(kuid)) return coord.url();
  }
  return null;
};

// -- CRD-02: reject -------------------------------------------------------------------
let at = await findCase();
check(`CRD-02 finds ${kuid} in the queue`, Boolean(at));
if (at) {
  const reason = "The ID document photo is too blurred to read the name. Please take it again in better light.";
  await coord.fill("#reason", reason); // typing the reason, then
  await Promise.all([coord.waitForLoadState("load"), coord.click("button[value=reject]")]); // tap 1
  check("CRD-02 reject: the reason plus one tap", (await text(coord)).includes("rejected"));

  // -- VER-05: the athlete sees it and resubmits ------------------------------------
  await athlete.goto(`${BASE}/verify`, { waitUntil: "load" });
  const ver = await athlete.locator("main").innerText();
  check("VER-05 shows the reviewer's reason verbatim", ver.includes(reason));
  check("VER-05 says, in bold, that there is no second fee", (await athlete.locator("strong", { hasText: "You do not pay again." }).count()) > 0);
  await Promise.all([athlete.waitForLoadState("load"), athlete.locator("button", { hasText: "Resubmit for review" }).click()]);
  check("the athlete resubmits and is back under review", (await text(athlete)).includes("under review"));

  // -- CRD-02: approve ------------------------------------------------------------------
  at = await findCase();
  // The browser blocks the submit until the box is ticked (the action refuses it too).
  check("CRD-02 will not approve without the check tick", (await coord.locator("#checked").getAttribute("required")) !== null);
  await coord.locator("label[for=checked]").click(); // tap 1
  await Promise.all([coord.waitForLoadState("load"), coord.click("button[value=approve]")]); // tap 2
  check("CRD-02 approve: two taps (tick, approve)", (await text(coord)).includes("approved"));

  await athlete.goto(`${BASE}/verify`, { waitUntil: "load" });
  check("VER-04 → approved: the athlete is verified", (await text(athlete)).includes("you are verified"));
  const photo = await athlete.request.get(`${BASE}/photo/${kuid}`);
  check(`the approved photo is now public (${photo.status()})`, photo.status() === 200);
}

// -- CRD-03 and CRD-04 ------------------------------------------------------------------
await coord.goto(`${BASE}/coordinator/find?q=${encodeURIComponent(kuid ?? "")}`, { waitUntil: "load" });
check("CRD-03 finds the athlete by ID within the LGA", (await coord.locator("main").innerText()).includes(kuid ?? "~"));
await coord.goto(`${BASE}/coordinator/find?q=KA-NG-JG-XXX-2026-000001`, { waitUntil: "load" });
check("CRD-03: an ID that is not in the LGA is simply no results", (await text(coord)).includes("no results"));

if (CASH_KUID) {
  // From the search result: tick "Cash collected" (tap 1), tap Pay (tap 2).
  await coord.goto(`${BASE}/coordinator/find?q=${encodeURIComponent(CASH_KUID)}`, { waitUntil: "load" });
  const row = coord.locator("form").filter({ has: coord.locator(`input[name=kuid][value="${CASH_KUID}"]`) });
  check("CRD-04 will not charge before the cash tick", (await row.locator("input[name=cash_collected]").getAttribute("required")) !== null);
  await row.locator("label").click(); // tap 1
  await Promise.all([coord.waitForURL(/paystack\.com|assist-pay\?/, { timeout: 120_000 }), row.locator("button[type=submit]").click()]); // tap 2
  const url = coord.url();
  check(`CRD-04 cash in two taps from the result: hands off to Paystack, or says why not (${url.includes("paystack") ? "Paystack" : decodeURIComponent(new URL(url).searchParams.get("error") ?? "")})`,
    url.includes("paystack.com") || url.includes("error="));
} else {
  console.log("  skip  the cash route (set CASH_KUID)");
}

await browser.close();
console.log(failed ? `\n${failed} FAILED` : "\nall passed");
process.exit(failed ? 1 : 0);
