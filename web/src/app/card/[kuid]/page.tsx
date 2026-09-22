import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getProfile, type PublicProfile } from "@/lib/api";

export const metadata: Metadata = { title: "Your KAFRIADA card" };
export const dynamic = "force-dynamic";

/**
 * The card (AUT-03 + ATH-03) — the moment the product is delivered.
 *
 * Two things govern this page. **The free thing arrives first**: the ID is
 * handed over, printable, before anything is asked for. Putting the ₦2,500
 * request above it would depress registration, and registration volume is the
 * first gate the pilot is judged on.
 *
 * And the card is **designed to be printed and cut out**. In the pilot the
 * printed card is what people actually carry, so the print stylesheet is not an
 * afterthought — it is the delivery format.
 */
export default async function CardPage({
  params,
}: {
  params: Promise<{ kuid: string }>;
}) {
  const { kuid } = await params;

  let profile: PublicProfile;
  try {
    profile = await getProfile(kuid);
  } catch {
    notFound();
  }

  const firstName = profile.full_name.split(" ")[0];

  return (
    <div className="stack">
      <div className="no-print">
        <p className="eyebrow">Step 3 of 3 · Done</p>
        <h1>{`${firstName}, this is your ID.`}</h1>
        <p className="lede">
          It is permanent and it is yours. Print it, download it, or simply
          write the number down — all three work.
        </p>
      </div>

      {/* -- The card itself. This is what gets printed. ------------------- */}
      <article className="doc" aria-label="Your KAFRIADA card">
        <div className="doc__body">
          <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--s4)", alignItems: "flex-start" }}>
            <div style={{ minWidth: 0 }}>
              <p className="eyebrow" style={{ marginBottom: "var(--s2)" }}>
                Federation of Nigerian Sports
              </p>
              <h2 style={{ fontSize: "clamp(1.4rem, 5.5vw, 1.9rem)", marginBottom: "var(--s1)" }}>
                {profile.full_name}
              </h2>
              <p style={{ color: "var(--plate-muted)", margin: 0, fontSize: ".95rem" }}>
                {profile.sport}
                {profile.playing_position ? ` · ${profile.playing_position}` : ""}
              </p>
              <p style={{ color: "var(--plate-muted)", margin: "2px 0 0", fontSize: ".95rem" }}>
                {profile.lga_name}, {profile.state_name}
              </p>
            </div>

            <div className="seal" aria-hidden="true">
              <strong>KAF</strong>
              {profile.registered_year}
            </div>
          </div>

          <div
            style={{
              display: "flex", gap: "var(--s4)", alignItems: "center",
              marginTop: "var(--s5)", paddingTop: "var(--s5)",
              borderTop: "1px solid var(--plate-rule)", flexWrap: "wrap",
            }}
          >
            {/* Server-rendered, cached a day, and proxied — the browser never
                touches the domain tier to get it. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`/qr/${encodeURIComponent(profile.kuid)}`}
              alt={`QR code linking to the public profile for ${profile.kuid}`}
              width={132}
              height={132}
              style={{ width: 132, height: 132, flex: "none" }}
            />
            <div style={{ minWidth: 180, flex: 1 }}>
              <p className="eyebrow" style={{ marginBottom: "var(--s2)" }}>
                Scan to verify
              </p>
              <p style={{ fontSize: ".92rem", color: "var(--plate-muted)", marginBottom: 0 }}>
                Anyone can scan this with a phone camera to see your public
                profile. It does not show your phone number or your date of
                birth.
              </p>
            </div>
          </div>
        </div>

        <div className="doc__perf" />
        <div className="mrz">
          <small>KAFRIADA unique identifier</small>
          {profile.kuid}
        </div>
      </article>

      {/* -- Actions ------------------------------------------------------- */}
      <div className="no-print" style={{ display: "flex", gap: "var(--s3)", flexWrap: "wrap" }}>
        {/* A plain link to the print stylesheet route would need JavaScript to
            trigger window.print(). Instead the page IS the print layout, so the
            browser's own print command produces the card — which works
            everywhere, including where scripts do not run. */}
        <a href={`/a/${encodeURIComponent(profile.kuid)}`} className="btn btn--primary">
          View my public profile
        </a>
        {/* The full card — name, QR and KUID in one image — not just the code
            on its own. Plain downloads, so a PDF exists even on a browser
            with no "print to PDF" of its own (Opera Mini among them). */}
        <a href={`/card/${encodeURIComponent(profile.kuid)}/card.png`} className="btn btn--ghost" download>
          Download card (PNG)
        </a>
        <a href={`/card/${encodeURIComponent(profile.kuid)}/card.pdf`} className="btn btn--ghost" download>
          Download card (PDF)
        </a>
      </div>

      <div className="notice no-print">
        <p className="notice__title">To print</p>
        <p style={{ marginBottom: 0 }}>
          Use your browser&rsquo;s Print command on this page. Everything except
          the card is left off the paper automatically.
        </p>
      </div>

      {/* -- The upsell. Deliberately AFTER the free thing is delivered. --- */}
      <div className="notice notice--warn no-print">
        <p className="notice__title">Optional</p>
        <p>
          <strong>Add your photograph for ₦2,500.</strong> Your LGA coordinator
          checks your ID document, and your photo then appears on your public
          profile with a verified badge.
        </p>
        <p style={{ marginBottom: 0, fontSize: ".9rem", color: "var(--plate-muted)" }}>
          No bank card? Take ₦2,500 in cash to your LGA coordinator and they can
          do it for you. Payment opens shortly.
        </p>
      </div>

      <div className="notice no-print">
        <p className="notice__title">Keep this number</p>
        <p style={{ marginBottom: 0 }}>
          Your ID is <span className="kuid">{profile.kuid}</span>. It records
          where you first registered, not where you live — it stays the same even
          if you move or change clubs.
        </p>
      </div>
    </div>
  );
}
