// Club stage three with JavaScript off: links, a photo, and the hand-off to payment.
//
//   CLUB_ID=… REP_PHONE=… REP_PASSWORD=… PHOTO=path/to.jpg node scripts/e2e-club-stage3.mjs
//
// The club must already be approved and at stage two (on a local database:
// UPDATE identity.organizations SET status = 'approved', stage = 2 WHERE id = …).
// Run the API with MEDIA_STORE=local and PAYMENT_PROVIDER=fake. Writes to that club only.
import { chromium } from "playwright-core";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const { CLUB_ID, REP_PHONE, REP_PASSWORD, PHOTO } = process.env;
if (!CLUB_ID || !REP_PHONE || !REP_PASSWORD || !PHOTO) throw new Error("Set CLUB_ID, REP_PHONE, REP_PASSWORD and PHOTO.");

let failed = 0;
const check = (label, ok) => {
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${label}`);
  if (!ok) failed++;
};

const browser = await chromium.launch({ channel: "msedge" });
const context = await browser.newContext({ viewport: { width: 360, height: 780 }, isMobile: true, javaScriptEnabled: false });
const page = await context.newPage();
const main = async () => (await page.locator("main").innerText()).toLowerCase();

await page.goto(`${BASE}/sign-in`, { waitUntil: "load" });
await page.fill("#phone", REP_PHONE);
await page.fill("#password", REP_PASSWORD);
await Promise.all([page.waitForLoadState("load"), page.click("form button[type=submit]")]);
check(`signed in (${new URL(page.url()).pathname})`, !page.url().includes("/sign-in"));

const stage3 = `${BASE}/clubs/${CLUB_ID}/stage-three`;
await page.goto(`${BASE}/clubs/${CLUB_ID}`, { waitUntil: "load" });
check("CLB-02 shows the stage and offers stage three", (await main()).includes("stage 2") && (await page.locator(`a[href$="/stage-three"]`).count()) > 0);

await page.goto(stage3, { waitUntil: "load" });
check("the page explains what stage three gives", (await main()).includes("up to 70 players"));
check("paying waits for a link and a photo", await page.locator("form button[type=submit]").last().isDisabled());

await page.locator("input[name=links]").first().fill("https://example.com/club");
await Promise.all([page.waitForLoadState("load"), page.getByRole("button", { name: "Save links" }).click()]);
check(`links are saved (${new URL(page.url()).search})`, page.url().includes("saved=links"));
check("the link is kept in the form", (await page.locator("input[name=links]").first().inputValue()) === "https://example.com/club");

await page.setInputFiles("#photo", PHOTO);
await Promise.all([page.waitForLoadState("load"), page.getByRole("button", { name: "Upload photo" }).click()]);
check(`the photo is added (${new URL(page.url()).search})`, page.url().includes("saved=photo"));
const img = page.locator(`img[src*="/stage-three/photo/"]`);
check("the photo shows, through our own address", (await img.count()) === 1);
const shown = await page.request.get(new URL(await img.getAttribute("src"), BASE).toString());
check(`the photo route serves a JPEG (${shown.status()})`, shown.ok() && (shown.headers()["content-type"] ?? "").includes("image/jpeg"));

const pay = page.getByRole("button", { name: /^Pay / });
check("paying is open once both are there", !(await pay.isDisabled()));
// A real provider shows its own page; the fake one returns straight here with the reference.
const before = page.url();
await Promise.all([page.waitForURL((u) => u.toString() !== before, { timeout: 30_000 }), pay.click()]);
check(`the checkout hands off with our reference (${new URL(page.url()).host})`, !page.url().startsWith(stage3) || page.url().includes("reference=KAF-"));

await browser.close();
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
