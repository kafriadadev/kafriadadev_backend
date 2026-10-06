import { VerificationBadge } from "@/components/VerificationBadge";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PageHead } from "@/components/PageHead";
import { getProfile, type PublicProfile } from "@/lib/api";

export const metadata: Metadata = { title: "Your KAFRIADA NET card" };
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
    <div>
      <div>
        <PageHead
          eyebrow="Step 3 of 3 · Done"
          title={`${firstName}, this is your ID.`}
          lede="It is permanent and it is yours. Print it, download it, or simply write the number down. All three work."
        />
        <p>
          <span>Status</span>
          <VerificationBadge verified={profile.is_verified} />
        </p>
      </div>

      <div>
      <div>

      {/* -- The card itself. This is what gets printed. ------------------- */}
      <article aria-label="Your KAFRIADA NET card">
        <div>
          <div>
            <div>
              <p>
                Federation of Nigerian Sports
              </p>
              <h2>
                {profile.full_name}
              </h2>
              <p>
                {profile.sport}
                {profile.playing_position ? ` · ${profile.playing_position}` : ""}
              </p>
              <p>
                {profile.lga_name}, {profile.state_name}
              </p>
            </div>

          </div>

          <div>
            {/* Server-rendered, cached a day, and proxied — the browser never
                touches the domain tier to get it. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`/qr/${encodeURIComponent(profile.kuid)}`}
              alt={`QR code linking to the public profile for ${profile.kuid}`}
              width={132}
              height={132}
            />
            <div>
              <p>
                Scan to verify
              </p>
              <p>
                Anyone can scan this with a phone camera to see your public
                profile. It does not show your phone number or your date of
                birth.
              </p>
            </div>
          </div>
        </div>

      </article>

      {/* -- Actions ------------------------------------------------------- */}
      <div>
        {/* A plain link to the print stylesheet route would need JavaScript to
            trigger window.print(). Instead the page IS the print layout, so the
            browser's own print command produces the card — which works
            everywhere, including where scripts do not run. */}
        <a href={`/a/${encodeURIComponent(profile.kuid)}`}>
          View my public profile
        </a>
        {/* The full card — name, QR and KUID in one image — not just the code
            on its own. Plain downloads, so a PDF exists even on a browser
            with no "print to PDF" of its own (Opera Mini among them). */}
        <a href={`/card/${encodeURIComponent(profile.kuid)}/card.png`} download>
          Download card (PNG)
        </a>
        <a href={`/card/${encodeURIComponent(profile.kuid)}/card.pdf`} download>
          Download card (PDF)
        </a>
      </div>

      </div>

      <aside>
      <div>
        <p>To print</p>
        <p>
          Use your browser&rsquo;s Print command on this page. Everything except
          the card is left off the paper automatically.
        </p>
      </div>

      {/* -- The upsell. Deliberately AFTER the free thing is delivered. --- */}
      {profile.is_verified ? null : (
      <div>
        <p>Get verified</p>
        <p>
          <strong>Your profile shows as unverified.</strong> For ₦2,500 your LGA
          coordinator checks your ID document, and your profile then shows the
          verified badge and your photograph.
        </p>
        <p>
          No bank card? Take ₦2,500 in cash to your LGA coordinator and they can
          do it for you.
        </p>
        <a href="/verify">Get verified</a>
      </div>
      )}

      <div>
        <p>Keep this number</p>
        <p>
          Your ID is <span>{profile.kuid}</span>. It records
          where you first registered, not where you live — it stays the same even
          if you move or change clubs.
        </p>
      </div>
      </aside>
      </div>
    </div>
  );
}
