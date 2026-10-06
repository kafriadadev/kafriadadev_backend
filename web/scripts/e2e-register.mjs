// A complete registration with JavaScript OFF: AUT-01 -> AUT-02 -> AUT-03.
//
//   node scripts/e2e-register.mjs
//
// WRITES a real athlete (a throwaway phone and an @example.test email) to the
// database the API is using, so run it against a dev database only. The
// emailed code is read from ops.outbox by CODE_CMD, a command that prints it
// (it receives the email address as its last argument). Run the outbox
// dispatcher only after this, or the row may be delivered and scrubbed first.
// SHOT_DIR=<dir> also saves full-page screenshots of AUT-03 and PUB-01.
import { chromium } from "playwright-core";
import { execFileSync } from "node:child_process";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const CODE_CMD = (process.env.CODE_CMD ?? "").split(" ").filter(Boolean);
if (!CODE_CMD.length) throw new Error("Set CODE_CMD, e.g. CODE_CMD='python scripts/code_for.py'");

const n = String(Math.floor(Math.random() * 1e7)).padStart(7, "0");
const phone = `0803${n}`;
const email = `e2e.${n}@example.test`;

const browser = await chromium.launch({ channel: "msedge" });
const ctx = await browser.newContext({ viewport: { width: 360, height: 780 }, isMobile: true, javaScriptEnabled: false });
const page = await ctx.newPage();
let failed = 0;
const check = (label, ok) => {
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${label}`);
  if (!ok) failed++;
};

await page.goto(`${BASE}/register`, { waitUntil: "load" });
const fill = { first_name: "Endtoend", surname: "Nojs", date_of_birth: "1999-05-20", town: "Birnin Kudu", address_line: "1 Test Road",
  email, emergency_name: "Test Guardian", emergency_relationship: "Brother", emergency_phone: "08030000001",
  years_experience: "4", height_cm: "178", weight_kg: "70", password: "a long test phrase 42" };
for (const [id, value] of Object.entries(fill)) await page.fill(`#${id}`, value);
await page.fill("#phone", phone);
await page.selectOption("#gender", "male");
await page.selectOption("#state_of_origin", "Jigawa");
const lga = await page.locator("#lga_id optgroup").first().locator("option").first().getAttribute("value");
await page.selectOption("#lga_id", lga);
await page.selectOption("#level_played", { index: 1 });
await page.selectOption("#dominant_side", "right");
await page.locator("label[for='playing_position-3']").click(); // Central midfielder, tapped on the pitch
await page.locator("label[for='accept_privacy_notice']").click();
await Promise.all([page.waitForLoadState("load"), page.click("form button[type=submit]")]);
check(`AUT-01 submits with JavaScript off and lands on AUT-02 (${new URL(page.url()).pathname})`, page.url().includes("/register/confirm"));

const code = execFileSync(CODE_CMD[0], [...CODE_CMD.slice(1), email], { encoding: "utf8" }).trim();
check(`the emailed code was queued (${code ? "found" : "missing"})`, /^\d{6}$/.test(code));
await page.fill("#code", code);
await Promise.all([page.waitForLoadState("load"), page.locator("form").first().locator("button[type=submit]").click()]);
check(`AUT-02 confirms and lands on AUT-03 (${new URL(page.url()).pathname})`, page.url().includes("/register/done"));

if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/aut-03.png`, fullPage: true });
const kuid = (await page.locator("article").first().innerText()).match(/KA-NG-[A-Z]{2}-[A-Z]{3}-\d{4}-\d{6}/)?.[0];
check(`AUT-03 shows the new ID (${kuid ?? "none"})`, Boolean(kuid));
check("AUT-03 shows Central midfielder on the card", (await page.locator("article").first().innerText()).includes("Central midfielder"));
const share = await page.locator("a[href^='https://wa.me/']").getAttribute("href");
check("AUT-03 offers a WhatsApp share link to the profile", Boolean(share && decodeURIComponent(share).includes(`/a/${kuid}`)));
check("AUT-03 shows the price only after the ID", (await page.content()).indexOf("₦2,500") > (await page.content()).indexOf(kuid ?? "~"));

const profile = await page.goto(`${BASE}/a/${kuid}`, { waitUntil: "load" });
check(`PUB-01 renders the new athlete (HTTP ${profile?.status()})`, profile?.status() === 200);
if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/pub-01.png`, fullPage: true });
const og = await page.locator("meta[property='og:image']").getAttribute("content");
const img = og ? await page.request.get(og) : null;
check(`the WhatsApp preview image is a PNG (${img?.headers()["content-type"]})`, img?.headers()["content-type"] === "image/png");

await browser.close();
console.log(failed ? `\n${failed} FAILED` : `\nall passed · registered ${kuid} (${phone})`);
process.exit(failed ? 1 : 0);
