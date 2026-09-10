import Link from "next/link";

/**
 * The landing page (PUB-02).
 *
 * Most people arrive here from a poster or from someone telling them, not from
 * a search. So it answers three questions immediately — what this is, what it
 * costs, and how to start — and then gets out of the way.
 */
export default function Home() {
  return (
    <div className="stack">
      <p className="eyebrow">Kowa Guru Technology · Federation of Nigerian Sports</p>
      <h1>
        Your permanent
        <br />
        sports identity.
      </h1>
      <p className="lede">
        Register once and receive a KAFRIADA ID that is yours for life. Print it,
        carry it, and any club or scout can check it in seconds.
      </p>

      <p>
        <strong>Registration is free.</strong> It takes about two minutes and you
        need a phone that can receive SMS.
      </p>

      <div style={{ display: "flex", gap: "var(--s3)", flexWrap: "wrap" }}>
        <Link href="/register" className="btn btn--primary">
          Register free
        </Link>
        <Link href="/find" className="btn btn--ghost">
          Look up an ID
        </Link>
      </div>

      <section className="doc" style={{ marginTop: "var(--s7)" }}>
        <div className="doc__body">
          <p className="eyebrow" style={{ marginBottom: "var(--s4)" }}>How it works</p>
          <ol className="stack" style={{ paddingLeft: "1.1em", margin: 0 }}>
            <li>
              <strong>Register.</strong> Your name, your phone, your LGA. Nothing else.
            </li>
            <li>
              <strong>Receive your ID.</strong> A number like{" "}
              <span className="kuid">KA-NG-JG-BKD-2026-000123</span> that never changes.
            </li>
            <li>
              <strong>Print your card.</strong> Anyone can scan the code and see your
              profile — without needing an account.
            </li>
          </ol>
        </div>
        <div className="doc__perf" />
        <div className="mrz">
          <small>Issuing authority</small>
          KAFRIADA · FEDERATION OF NIGERIAN SPORTS
        </div>
      </section>

      <div className="notice notice--warn">
        <p className="notice__title">Optional, later</p>
        <p style={{ marginBottom: 0 }}>
          Once registered you can add your photograph and a verified badge for
          ₦2,500 — checked by your LGA coordinator. Your ID works either way.
        </p>
      </div>
    </div>
  );
}
