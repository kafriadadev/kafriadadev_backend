import type { AppProps } from "next/app";
import { fontRootCss } from "@/app/fonts";
import "@/app/globals.css";

/**
 * The Pages Router exists for one reason: a page here can ship zero
 * JavaScript (`unstable_runtimeJS: false`), which the App Router cannot. The
 * public pages a stranger lands on live here: the landing page, the public
 * profile, find, sign in and register. Their forms post to /forms/{name}, which
 * runs the same server actions. Same tokens, same components.
 */
export default function App({ Component, pageProps }: AppProps) {
  return (
    <>
      {/* Server-rendered, so it works with the runtime switched off. */}
      <style dangerouslySetInnerHTML={{ __html: fontRootCss }} />
      <Component {...pageProps} />
    </>
  );
}
