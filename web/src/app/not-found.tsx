import Link from "next/link";

/** PUB-05 for a missing record. Never alarming, always with a way forward. */
export default function NotFound() {
  return (
    <div className="stack">
      <p className="eyebrow">Not found</p>
      <h1>No athlete with that ID</h1>
      <p className="lede">
        Check the ID printed on the card and try again. A KAFRIADA ID looks like{" "}
        <span className="kuid">KA-NG-JG-BKD-2026-000123</span>.
      </p>
      <div style={{ display: "flex", gap: "var(--s3)", flexWrap: "wrap" }}>
        <Link href="/find" className="btn btn--primary">Look up an ID</Link>
        <Link href="/" className="btn btn--ghost">Back to home</Link>
      </div>
    </div>
  );
}
