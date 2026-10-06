import { VerificationBadge } from "@/components/VerificationBadge";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getProfile, type PublicProfile } from "@/lib/api";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined) =>
  Array.isArray(v) ? v[0] : v;

/**
 * The public profile (PUB-01) — where a scanned QR code lands.
 *
 * The highest-traffic page in the system and the only one a stranger ever sees.
 * No account, no JavaScript, no cookie. Someone standing at a pitch side with a
 * cheap phone and one bar of signal must get an answer.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ kuid: string }>;
}): Promise<Metadata> {
  const { kuid } = await params;
  try {
    const p = await getProfile(kuid);
    return {
      title: `${p.full_name} · ${p.kuid}`,
      description: `${p.full_name}, ${p.sport}${p.playing_position ? ` (${p.playing_position})` : ""}, ${p.lga_name}, ${p.state_name}. Registered with KAFRIADA NET in ${p.registered_year}.`,
    };
  } catch {
    return { title: "Athlete not found" };
  }
}

export const revalidate = 60; // matches the edge cache the architecture assumes

export default async function ProfilePage({
  params,
  searchParams,
}: {
  params: Promise<{ kuid: string }>;
  searchParams: Promise<Search>;
}) {
  const { kuid } = await params;
  const signature = one((await searchParams).s);

  let profile: PublicProfile;
  try {
    profile = await getProfile(kuid, signature);
  } catch {
    // A malformed ID and a real one that does not exist give the same answer.
    // Distinguishing them would let anyone walk the register by guessing.
    notFound();
  }

  return (
    <div>
      <article>
        <div>
          <div>
            {profile.is_verified && profile.photo_url ? (
              <div>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/photo/${encodeURIComponent(profile.kuid)}`}
                  alt={`Photograph of ${profile.full_name}`}
                  width={96}
                  height={116}
                />
              </div>
            ) : (
              <p>No photograph on file</p>
            )}

            <div>
              <p>
                Registered athlete
              </p>
              <h1>
                {profile.full_name}
              </h1>
              <p>
                {profile.sport}
                {profile.playing_position ? ` · ${profile.playing_position}` : ""}
              </p>

              <p>
                <VerificationBadge verified={profile.is_verified} />
                {profile.issued_by_kafriada ? (
                  <span>
                    <Tick /> Issued by KAFRIADA NET
                  </span>
                ) : (
                  <span>Unsigned link</span>
                )}
              </p>
            </div>
          </div>

          {/* The wording here is a security control, not copy.
              A valid signature proves the QR came from us. It does NOT prove
              the person holding the card is the person named, because a card
              can be photocopied and the signature copied with it. Saying
              "verified athlete" here would mislead a scout. */}
          <div
          >
            <p>
              {profile.issued_by_kafriada ? "This code is genuine" : "About this page"}
            </p>
            <p>
              {profile.issued_by_kafriada
                ? "This QR code was issued by KAFRIADA NET. Check that the photograph matches the person in front of you."
                : "This page was opened without a KAFRIADA NET QR code, so we cannot confirm where the link came from. The record below is still correct."}
            </p>
          </div>

          <dl>
            <div>
              <dt>KAFRIADA NET ID</dt>
              <dd>{profile.kuid}</dd>
            </div>
            <div>
              <dt>Age</dt>
              <dd>{profile.age}</dd>
            </div>
            <div>
              <dt>Registered</dt>
              <dd>{profile.lga_name}, {profile.state_name}</dd>
            </div>
            <div>
              <dt>Since</dt>
              <dd>{profile.registered_year}</dd>
            </div>
            <div>
              <dt>Identity</dt>
              <dd>
                {profile.is_verified ? (
                  "Checked by the LGA coordinator"
                ) : profile.verification_withdrawn ? (
                  "Verification withdrawn"
                ) : (
                  <span>Not yet checked</span>
                )}
              </dd>
            </div>
          </dl>
        </div>

      </article>

      <p>
        This page shows only what an athlete has agreed to publish. It never
        shows a phone number, a date of birth or any identity document.
      </p>

      <p>
        <a href="/register">Get your own KAFRIADA NET ID</a>
      </p>
    </div>
  );
}

function Tick() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path
        d="M2 8.5l4 4L14 4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
