import { Flash } from "./Flash";

/** What a signed-in person sees on a screen their roles do not reach. */
export function NoAccess({
  title,
  message = "Only a super administrator can open this.",
}: {
  title: string;
  message?: string;
}) {
  return (
    <div className="page stack">
      <h1>{title}</h1>
      <Flash variant="bad" title="You do not have access to this">
        <p className="mb0">{message}</p>
      </Flash>
      <p><a href="/me">Back to my account</a></p>
    </div>
  );
}
