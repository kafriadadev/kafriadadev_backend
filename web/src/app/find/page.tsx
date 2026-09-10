import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Look up an athlete" };

/**
 * PUB-03 — a way in for someone whose camera will not scan, or whose card has
 * a damaged code. A plain GET form, so it works everywhere and the result is a
 * shareable address.
 */
export default function FindPage() {
  async function find(formData: FormData) {
    "use server";
    const raw = String(formData.get("kuid") ?? "").trim().toUpperCase();
    // Tidy what a person actually types off a card before looking it up. The
    // API does the same normalisation; doing it here too means the address bar
    // ends up clean rather than carrying their typing.
    const cleaned = raw.replace(/[\u2010-\u2015_\s]+/g, "-").replace(/-{2,}/g, "-");
    if (!cleaned) redirect("/find?empty=1");
    redirect(`/a/${encodeURIComponent(cleaned)}`);
  }

  return (
    <div className="stack">
      <p className="eyebrow">Public lookup</p>
      <h1>Look up an athlete</h1>
      <p className="lede">
        Enter the KAFRIADA ID printed on the card. No account needed.
      </p>

      <form action={find} className="doc">
        <div className="doc__body">
          <div className="field">
            <label htmlFor="kuid">KAFRIADA ID</label>
            <span className="hint" id="kuid-hint">
              For example KA-NG-JG-BKD-2026-000123. Capital letters and dashes.
            </span>
            <input
              id="kuid"
              name="kuid"
              required
              autoComplete="off"
              spellCheck={false}
              placeholder="KA-NG-JG-___-____-______"
              aria-describedby="kuid-hint"
              style={{ fontFamily: "var(--font-mono)", letterSpacing: ".04em" }}
            />
          </div>
          <button type="submit" className="btn btn--primary btn--block">
            Look up
          </button>
        </div>
      </form>

      <p className="hint" style={{ color: "var(--muted)" }}>
        Easier still: point your phone camera at the QR code on the card.
      </p>
    </div>
  );
}
