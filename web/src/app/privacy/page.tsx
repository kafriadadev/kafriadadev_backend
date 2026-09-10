import type { Metadata } from "next";

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
    <div className="stack">
      <p className="eyebrow">Version 1.0 · Effective 1 October 2026</p>
      <h1>What we keep, and what we do with it</h1>

      <h3>What we collect</h3>
      <p>
        Your name, phone number, date of birth, Local Government Area, sport and
        position. If you choose paid verification, also a photograph and a
        photograph of an identity document.
      </p>

      <h3>What is public</h3>
      <p>
        Your name, KAFRIADA ID, sport, position, LGA, age and — once verified —
        your photograph. <strong>Your phone number and your date of birth are
        never shown publicly</strong>, and neither is any identity document.
      </p>

      <h3>Why we keep it</h3>
      <p>
        To issue and maintain your permanent sports identity, to check the
        documents you send for verification, and to keep records of payments as
        the law requires.
      </p>

      <div className="notice notice--warn">
        <p className="notice__title">If you ask us to delete your data</p>
        <p>
          Your name, photograph, phone number, date of birth and any documents
          are erased.
        </p>
        <p style={{ marginBottom: 0 }}>
          <strong>Your KAFRIADA ID and your payment records are kept.</strong> We
          are required to retain financial records, and the record of what
          happened cannot be altered by anyone — including us. We are telling you
          this before you register rather than after you ask.
        </p>
      </div>

      <h3>How long</h3>
      <p>
        Identity documents are deleted 30 days after a verification decision.
        Records of what happened are kept for seven years.
      </p>

      <h3>Who to contact</h3>
      <p>
        Speak to your LGA coordinator, or write to KowaGuru Technology Limited.
      </p>
    </div>
  );
}
