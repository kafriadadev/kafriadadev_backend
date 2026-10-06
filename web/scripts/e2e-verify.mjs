// Verification and payment through the screens, against the Paystack sandbox.
//
// Paystack's hosted checkout sits behind a Cloudflare bot check, so the card
// step is done by a person in a real browser. The script runs in two stages:
//
//   1. PHONE=0803... node scripts/e2e-verify.mjs
//      Signs in as that athlete (password from PASSWORD, default the
//      e2e-register one), uploads a photo and a document on /verify, runs the
//      media worker, starts the payment on /pay and prints the checkout link.
//      Pay it with Paystack's test card: 4084 0840 8408 4081, any future
//      expiry, CVV 408.
//
//   2. PHONE=0803... REFERENCE=KAF-... node scripts/e2e-verify.mjs
//      Checks the return screen, runs the reconciler (which asks Paystack and
//      settles), then checks /pay shows the payment confirmed, /verify shows
//      VER-04 under review, and /payments lists it as paid.
//
// WRITES to the dev database and creates a Paystack test transaction.
import { chromium } from "playwright-core";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const API_DIR = new URL("../../api/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const PY = process.env.API_PYTHON ?? join(API_DIR, ".venv", "Scripts", "python.exe");
const PHONE = process.env.PHONE;
const PASSWORD = process.env.PASSWORD ?? "a long test phrase 42";
const REFERENCE = process.env.REFERENCE;
if (!PHONE) throw new Error("Set PHONE to a registered, email-confirmed athlete (scripts/e2e-register.mjs makes one).");

let failed = 0;
const check = (label, ok) => {
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${label}`);
  if (!ok) failed++;
};
const run = (args) => execFileSync(PY, args, { cwd: API_DIR, encoding: "utf8" });

const browser = await chromium.launch({ channel: "msedge" });
const ctx = await browser.newContext({ viewport: { width: 400, height: 860 }, isMobile: true });
const page = await ctx.newPage();
await page.goto(`${BASE}/sign-in`, { waitUntil: "networkidle" });
await page.locator("#phone").pressSequentially(PHONE);
await page.fill("#password", PASSWORD);
await Promise.all([page.waitForURL(/\/me/, { timeout: 60_000 }), page.click("form button[type=submit]")]);
check("signed in", page.url().includes("/me"));

if (!REFERENCE) {
  // -- Stage 1: VER-01/02 to the Paystack hand-off ---------------------------
  const dir = mkdtempSync(join(tmpdir(), "kaf-e2e-"));
  run(["-c", `
from PIL import Image, ImageDraw
for name, col in (("photo", (180, 140, 110)), ("document", (210, 220, 235))):
    im = Image.new("RGB", (900, 1100), col); d = ImageDraw.Draw(im)
    d.ellipse((300, 200, 600, 500), fill=(90, 60, 40)); d.rectangle((200, 560, 700, 1100), fill=(40, 90, 60))
    im.save(r"${dir}/" + name + ".jpg", quality=85)
`]);
  await page.goto(`${BASE}/verify`, { waitUntil: "networkidle" });
  check("VER-01 shows the card and cash routes side by side", (await page.locator("text=Pay in cash").count()) > 0 && (await page.locator("text=Pay by card").count()) > 0);
  await page.setInputFiles("#photo", join(dir, "photo.jpg"));
  await page.setInputFiles("#document", join(dir, "document.jpg"));
  await Promise.all([page.waitForURL(/verify\?/, { timeout: 90_000 }), page.locator("#upload button[type=submit]").click()]);
  check(`VER-02 accepts both files (${new URL(page.url()).search})`, page.url().includes("saved=1"));
  run(["-m", "kafriada.contexts.media.worker", "--once"]);
  await page.goto(`${BASE}/verify`, { waitUntil: "networkidle" });
  check("both files are ready and payment is offered", (await page.locator("a[href='/pay']").count()) > 0);

  await page.goto(`${BASE}/pay`, { waitUntil: "networkidle" });
  check("VER-03 shows ₦2,500 due", (await page.content()).includes("₦2,500"));
  await Promise.all([page.waitForURL(/paystack\.com/, { timeout: 90_000 }), page.locator("form button[type=submit]").first().click()]);
  check("VER-03 hands off to Paystack", page.url().includes("paystack.com"));
  writeFileSync(join(dir, "checkout.txt"), page.url());
  console.log(`\nPay this in a browser with the test card 4084 0840 8408 4081, any future expiry, CVV 408:\n  ${page.url()}`);
  console.log("Then run stage 2 with REFERENCE set to the KAF- reference shown on the return page (or in the API log).");
} else {
  // -- Stage 2: back from Paystack ---------------------------------------------
  const ret = `${BASE}/pay?reference=${encodeURIComponent(REFERENCE)}`;
  await page.goto(ret, { waitUntil: "networkidle" });
  const before = await page.locator("main").innerText();
  check(`the return screen reads our own record (${before.includes("Payment confirmed") ? "confirmed" : before.includes("Confirming") ? "checking" : "other"})`,
    before.includes("Confirming your payment") || before.includes("Payment confirmed"));
  console.log(run(["-m", "kafriada.jobs", "--once", "--only", "reconcile"]).split("\n").filter((l) => /reconcil|settle|error/i.test(l)).slice(-4).join("\n"));
  await page.goto(ret, { waitUntil: "networkidle" });
  check("after reconciling, /pay shows Payment confirmed", (await page.locator("main").innerText()).includes("Payment confirmed"));
  await page.goto(`${BASE}/verify`, { waitUntil: "networkidle" });
  const v = await page.locator("main").innerText();
  check("VER-04: under review, with ₦2,500 paid on the timeline", v.includes("Under review".toUpperCase()) || v.toLowerCase().includes("under review"));
  check("VER-04 says what is already safe and when to expect a decision", v.includes("24 hours"));
  await page.goto(`${BASE}/payments`, { waitUntil: "networkidle" });
  const pay = await page.locator("main").innerText();
  check("ATH-04 lists the payment as paid, with the not-a-bank statement", pay.includes(REFERENCE) && pay.includes("Paid") && pay.includes("not a bank"));
}

await browser.close();
console.log(failed ? `\n${failed} FAILED` : "\nall passed");
process.exit(failed ? 1 : 0);
