import Link from "next/link";

/** PUB-05 for a missing record. Never alarming, always with a way forward. */
export default function NotFound() {
  return (
    <div>
      <p>Not found</p>
      <h1>No athlete with that ID</h1>
      <p>
        Check the ID printed on the card and try again. A KAFRIADA NET ID looks like{" "}
        <span>KA-NG-JG-BKD-2026-000123</span>.
      </p>
      <div>
        <Link href="/find">Look up an ID</Link>
        <Link href="/">Back to home</Link>
      </div>
    </div>
  );
}
