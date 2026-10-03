import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PageHead } from "@/components/PageHead";
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
    <div className="page page--wide">
      <div className="no-print">
        <PageHead
          eyebrow="Step 3 of 3 · Done"
          title={`${firstName}, this is your ID.`}
          lede="It is permanent and it is yours. Print it, download it, or simply write the number down. All three work."
        />
      </div>

      <div className="split">
      <div className="stack">

      {/* -- The card itself. This is what gets printed. ------------------- */}
      <article className="doc" aria-label="Your KAFRIADA card">
        <div className="doc__body">
          <div className="row-between">
            <div className="minw0">
              <p className="eyebrow mb-2">
                Federation of Nigerian Sports
              </p>
              <h2 className="doc__title">
                {profile.full_name}
              </h2>
              <p className="doc__sub">
                {profile.sport}
                {profile.playing_position ? ` · ${profile.playing_position}` : ""}
              </p>
              <p className="doc__sub">
                {profile.lga_name}, {profile.state_name}
              </p>
            </div>

            <div className="seal" aria-hidden="true">
              <strong>KAF</strong>
              {profile.registered_year}
            </div>
          </div>

          <div className="doc__section cluster cluster--lg">
            {/* Server-rendered, cached a day, and proxied — the browser never
                touches the domain tier to get it. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`/qr/${encodeURIComponent(profile.kuid)}`}
              alt={`QR code linking to the public profile for ${profile.kuid}`}
              width={132}
              height={132}
              className="qr"
            />
            <div className="grow">
              <p className="eyebrow mb-2">
                Scan to verify
              </p>
              <p className="hint mb0">
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
      <div className="no-print cluster">
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

      </div>

      <aside className="stack no-print">
      <div className="notice">
        <p className="notice__title">To print</p>
        <p className="mb0">
          Use your browser&rsquo;s Print command on this page. Everything except
          the card is left off the paper automatically.
        </p>
      </div>

      {/* -- The upsell. Deliberately AFTER the free thing is delivered. --- */}
      <div className="notice notice--warn">
        <p className="notice__title">Optional</p>
        <p>
          <strong>Add your photograph for ₦2,500.</strong> Your LGA coordinator
          checks your ID document, and your photo then appears on your public
          profile with a verified badge.
        </p>
        <p className="hint mb0">
          No bank card? Take ₦2,500 in cash to your LGA coordinator and they can
          do it for you.
        </p>
      </div>

      <div className="notice">
        <p className="notice__title">Keep this number</p>
        <p className="mb0">
          Your ID is <span className="kuid">{profile.kuid}</span>. It records
          where you first registered, not where you live — it stays the same even
          if you move or change clubs.
        </p>
      </div>
      </aside>
      </div>
    </div>
  );
}
