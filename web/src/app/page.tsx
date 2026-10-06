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
    <div>
      <section>
        <div>
          <p>Kowa Guru Technology · Federation of Nigerian Sports</p>
          <h1>
            Your permanent football ID. Free.
          </h1>
          <p>
            Register once and receive a KAFRIADA NET ID that is yours for life. Print it,
            carry it, and any club or scout can check it in seconds.
          </p>
          <p>
            <strong>Registration is free.</strong> It takes about two minutes and you
            need a phone that can receive SMS.
          </p>
          <div>
            <Link href="/register">Register free</Link>
            <Link href="/find">Look up an ID</Link>
          </div>
        </div>

      </section>

      <section aria-labelledby="how">
        <p id="how">How it works</p>
        <div>
          <div>
            <span aria-hidden="true">1</span>
            <h3>Register</h3>
            <p>Your name, your phone, your LGA. Nothing else.</p>
          </div>
          <div>
            <span aria-hidden="true">2</span>
            <h3>Receive your ID</h3>
            <p>
              A number like <span>KA-NG-JG-BKD-2026-000123</span> that
              never changes.
            </p>
          </div>
          <div>
            <span aria-hidden="true">3</span>
            <h3>Print your card</h3>
            <p>Anyone can scan the code and see your profile, without needing an account.</p>
          </div>
        </div>
      </section>

      <section aria-label="Verification">
        <div>
          <div>
            <p>Optional, later</p>
            <p>
              Once registered you can add your photograph and a verified badge for
              ₦2,500, checked by your LGA coordinator. Your ID works either way.
            </p>
          </div>
          <div>
            <p>For clubs</p>
            <p>
              Register your club, add your players and get a verified club badge. To check
              any player, scan the QR code on their card or{" "}
              <Link href="/find">look up an ID</Link>.
            </p>
            <Link href="/clubs/register">Register a club</Link>
          </div>
        </div>
      </section>
    </div>
  );
}
