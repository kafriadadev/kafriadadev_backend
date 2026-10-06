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
    <div>
      <h1>{title}</h1>
      <Flash variant="bad" title="You do not have access to this">
        <p>{message}</p>
      </Flash>
      <p><a href="/me">Back to my account</a></p>
    </div>
  );
}
