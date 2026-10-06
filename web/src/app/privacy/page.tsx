import type { Metadata } from "next";

import { PageHead } from "@/components/PageHead";

export const metadata: Metadata = { title: "Privacy notice" };

/**
 * PUB-04 — version 1.0.
 *
 * The version number matters: consent is recorded as a row pointing at a
 * specific version, so this text must remain reachable as it read on the day
 * somebody agreed to it.
 */
export default function PrivacyPage() {
  return (
    <div>
      <PageHead eyebrow="Version 1.1 · Effective 3 October 2026" title="What we keep, and what we do with it" />

      <h2>What we collect</h2>
      <p>
        Your name, sex, date of birth, nationality and state of origin; your phone
        number, email and home address; your sport, positions, stronger side, height,
        weight, years playing and the highest level you have played; and the name,
        relationship and phone number of an emergency contact. If you choose paid
        verification, also a photograph and a photograph of an identity document.
      </p>

      <h2>What is public</h2>
      <p>
        Your name, KAFRIADA NET ID, sport, position, LGA, age and, once verified, your
        photograph. <strong>Your phone number, email, address, date of birth and
        emergency contact are never shown publicly</strong>, and neither is any
        identity document. Your LGA coordinator and KAFRIADA NET administrators can see
        your full record.
      </p>

      <h2>Why we keep it</h2>
      <p>
        To issue and maintain your permanent sports identity, to check the
        documents you send for verification, and to keep records of payments as
        the law requires.
      </p>

      <div>
        <p>If you ask us to delete your data</p>
        <p>
          Your name, photograph, contact details, address, date of birth, emergency
          contact and any documents are erased.
        </p>
        <p>
          <strong>Your KAFRIADA NET ID and your payment records are kept.</strong> We
          are required to retain financial records, and the record of what
          happened cannot be altered by anyone — including us. We are telling you
          this before you register rather than after you ask.
        </p>
      </div>

      <h2>How long</h2>
      <p>
        Identity documents are deleted 30 days after a verification decision.
        Records of what happened are kept for seven years.
      </p>

      <h2>Who to contact</h2>
      <p>
        Speak to your LGA coordinator, or write to KowaGuru Technology Limited.
      </p>
    </div>
  );
}
