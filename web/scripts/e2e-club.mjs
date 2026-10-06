// A club, end to end: CLB-01 sign-up with JavaScript OFF -> email code -> CLB-02.
//
//   CODE_CMD="api/.venv/Scripts/python.exe scripts/outbox_code.py" node scripts/e2e-club.mjs
//
// With ADMIN_PHONE/ADMIN_PASSWORD (a super administrator) and ATHLETE_PHONE (an
// athlete made by e2e-register.mjs, password "a long test phrase 42") it goes on:
// approves the club through the API, invites the athlete on CLB-03, the athlete
// accepts on ATH-05, and the squad on CLB-02 shows them.
//
// WRITES a club and its representative to the database the API is using.
import { chromium } from "playwright-core";
import { execFileSync } from "node:child_process";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const API = process.env.API_URL ?? "http://127.0.0.1:8010";
const CODE_CMD = (process.env.CODE_CMD ?? "").split(" ").filter(Boolean);
if (!CODE_CMD.length) throw new Error("Set CODE_CMD (see the header).");
const ATHLETE_PASSWORD = "a long test phrase 42";

let failed = 0;
const check = (label, ok) => {
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${label}`);
  if (!ok) failed++;
};
const n = String(Math.floor(Math.random() * 1e7)).padStart(7, "0");
const email = `club.${n}@example.com`;

const browser = await chromium.launch({ channel: "msedge" });
const club = await browser.newContext({ viewport: { width: 360, height: 780 }, isMobile: true, javaScriptEnabled: false });
const page = await club.newPage();

// -- CLB-01 ---------------------------------------------------------------------
await page.goto(`${BASE}/clubs/register`, { waitUntil: "load" });
const fill = {
  name: `E2E United ${n}`, short_name: `E2E${n.slice(0, 3)}`, year_founded: "2015", ground_name: "Township Stadium",
  ground_address: "Stadium Road", town: "Birnin Kudu", contact_phone: `0803${String((Number(n) + 1) % 1e7).padStart(7, "0")}`,
  club_email: `office.${n}@example.com`, official2_name: "Second Official", official2_phone: `0806${n}`,
  rep_first_name: "Club", rep_surname: "Rep", rep_phone: `0805${n}`, rep_email: email, password: "a long club phrase 42",
};
for (const [id, value] of Object.entries(fill)) await page.fill(`#${id}`, value);
for (const id of ["type", "category", "level", "official2_role", "rep_role"]) await page.selectOption(`#${id}`, { index: 1 });
await page.selectOption("#lga_id", { index: 1 });
await page.locator("input[name=age_groups]").first().check();
await page.locator("label[for='accept_privacy_notice']").click();
await Promise.all([page.waitForLoadState("load"), page.click("form button[type=submit]")]);
check(`CLB-01 submits with JavaScript off and asks for the email code (${new URL(page.url()).pathname})`, page.url().includes("/register/confirm"));

const code = execFileSync(CODE_CMD[0], [...CODE_CMD.slice(1), email], { encoding: "utf8" }).trim();
await page.fill("#code", code);
await Promise.all([page.waitForLoadState("load"), page.locator("form").first().locator("button[type=submit]").click()]);
await page.goto(`${BASE}/me`, { waitUntil: "load" });
const href = await page.locator("a[href^='/clubs/']").filter({ hasText: fill.name }).first().getAttribute("href").catch(() => null);
check(`the representative's account lists the club (${href})`, Boolean(href));
const clubId = href?.split("/")[2];

await page.goto(`${BASE}${href}`, { waitUntil: "load" });
const dash = (await page.locator("main").innerText()).toLowerCase(); // headings are set in capitals
check("CLB-02 shows the club, its scoreboard and that it waits for approval", dash.includes(fill.name.toLowerCase()));
check("CLB-02 says it is waiting for approval", dash.includes("waiting for approval"));
check("CLB-02 shows the empty bench", dash.includes("no players yet"));
await page.goto(`${BASE}${href}?tab=details`, { waitUntil: "load" });
check("the club details tab shows the record", (await page.locator("main").innerText()).includes("Township Stadium"));

// -- Approve, invite, accept (needs a super administrator) ---------------------------
if (process.env.ADMIN_PHONE && process.env.ADMIN_PASSWORD && process.env.ATHLETE_PHONE && clubId) {
  const signIn = async (ctx, phone, password) => {
    const p = await ctx.newPage();
    await p.goto(`${BASE}/sign-in`, { waitUntil: "load" });
    await p.fill("#phone", phone);
    await p.fill("#password", password);
    await Promise.all([p.waitForLoadState("load"), p.click("form button[type=submit]")]);
    return p;
  };
  const adminCtx = await browser.newContext({ javaScriptEnabled: false });
  await signIn(adminCtx, process.env.ADMIN_PHONE, process.env.ADMIN_PASSWORD);
  const token = (await adminCtx.cookies()).find((c) => c.name === "kaf_session")?.value;
  const approved = await fetch(`${API}/v1/admin/clubs/${clubId}/approve`, { method: "POST", headers: { authorization: `Bearer ${token}` } });
  check(`the club is approved (${approved.status})`, approved.status === 204);

  const athleteCtx = await browser.newContext({ viewport: { width: 360, height: 780 }, javaScriptEnabled: false });
  const athlete = await signIn(athleteCtx, process.env.ATHLETE_PHONE, ATHLETE_PASSWORD);
  await athlete.goto(`${BASE}/me`, { waitUntil: "load" });
  const kuid = (await athlete.locator("main").innerText()).match(/KA-NG-[A-Z]{2}-[A-Z]{3}-\d{4}-\d{6}/)?.[0];

  await page.goto(`${BASE}${href}/invite?q=${encodeURIComponent(kuid ?? "")}`, { waitUntil: "load" });
  check("CLB-03 finds the athlete by their exact ID", (await page.locator("main").innerText()).includes(kuid ?? "~"));
  await page.goto(`${BASE}${href}/invite?q=KA-NG-JG`, { waitUntil: "load" });
  check("CLB-03 never matches part of an ID", (await page.locator("main").innerText()).toLowerCase().includes("no player found"));
  await page.goto(`${BASE}${href}/invite?q=${encodeURIComponent(kuid ?? "")}`, { waitUntil: "load" });
  await Promise.all([page.waitForLoadState("load"), page.locator("form[action] button[type=submit]").last().click()]);
  check(`the invitation is sent (${new URL(page.url()).search})`, page.url().includes("invited=1"));

  await athlete.goto(`${BASE}/clubs`, { waitUntil: "load" });
  check("ATH-05 shows the invitation", (await athlete.locator("main").innerText()).includes(fill.name));
  await Promise.all([athlete.waitForLoadState("load"), athlete.locator("form").filter({ has: athlete.locator("input[value=accept]") }).locator("button").first().click()]);
  check("the athlete accepts and has a club", (await athlete.locator("main").innerText()).includes("You have joined the club"));

  await page.goto(`${BASE}${href}`, { waitUntil: "load" });
  check("CLB-02's squad shows the player", (await page.locator("main").innerText()).includes(kuid ?? "~"));
  await adminCtx.close();
  await athleteCtx.close();
} else {
  console.log("  skip  approve, invite and accept (set ADMIN_PHONE, ADMIN_PASSWORD and ATHLETE_PHONE)");
}

await browser.close();
console.log(failed ? `\n${failed} FAILED` : `\nall passed · club ${clubId} · representative ${fill.rep_phone}`);
process.exit(failed ? 1 : 0);
