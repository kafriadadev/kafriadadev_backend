import { RaisedFlag } from "./illustrations";
import { Button } from "./ui/Button";
import { PageState } from "./ui/PageState";

/** What a signed-in person sees on a screen their roles do not reach. */
export function NoAccess({ title, message = "Only a super administrator can open this." }: { title: string; message?: string }) {
  return (
    <PageState art={<RaisedFlag />} title={title} action={<Button href="/me" size="lg" block>My account</Button>}>
      {message}
    </PageState>
  );
}
