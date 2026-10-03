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
    <div className="page page--wide">
      <section className="hero">
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
          <div className="cluster">
            <Link href="/register" className="btn btn--primary">Register free</Link>
            <Link href="/find" className="btn btn--ghost">Look up an ID</Link>
          </div>
        </div>

        {/* A sample of what is issued — the product is the document. */}
        <div className="doc hero__card" aria-label="Example KAFRIADA card">
          <div className="doc__body">
            <div className="row-between">
              <div>
                <p className="eyebrow">Federation of Nigerian Sports</p>
                <h2 className="mb0">Aisha Musa</h2>
                <p className="hint mb0">Football · Midfielder</p>
                <p className="hint mb0">Birnin Kudu, Jigawa</p>
              </div>
              <div className="seal" aria-hidden="true">
                <strong>KAF</strong>
                2026
              </div>
            </div>
          </div>
          <div className="doc__perf" />
          <div className="mrz">
            <small>KAFRIADA unique identifier</small>
            KA-NG-JG-BKD-2026-000123
          </div>
        </div>
      </section>

      <section className="band" aria-labelledby="how">
        <p className="eyebrow" id="how">How it works</p>
        <div className="grid grid-3">
          <div className="step">
            <span className="step__num" aria-hidden="true">1</span>
            <h3>Register</h3>
            <p>Your name, your phone, your LGA. Nothing else.</p>
          </div>
          <div className="step">
            <span className="step__num" aria-hidden="true">2</span>
            <h3>Receive your ID</h3>
            <p>
              A number like <span className="kuid">KA-NG-JG-BKD-2026-000123</span> that
              never changes.
            </p>
          </div>
          <div className="step">
            <span className="step__num" aria-hidden="true">3</span>
            <h3>Print your card</h3>
            <p>Anyone can scan the code and see your profile, without needing an account.</p>
          </div>
        </div>
      </section>

      <section className="band" aria-label="Verification">
        <div className="split split--even">
          <div className="notice notice--warn">
            <p className="notice__title">Optional, later</p>
            <p className="mb0">
              Once registered you can add your photograph and a verified badge for
              ₦2,500, checked by your LGA coordinator. Your ID works either way.
            </p>
          </div>
          <div className="notice">
            <p className="notice__title">For clubs and scouts</p>
            <p className="mb0">
              Scan the QR code on a card, or <Link href="/find">look up an ID</Link>. No
              account is needed to check a player.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
