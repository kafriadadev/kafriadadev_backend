import { Head, Html, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en-NG">
      <Head>
        <link rel="icon" href="/brand/kafriada-net-mark.svg" />
      </Head>
      <body>
        <Main />
        {/* Renders nothing on pages with unstable_runtimeJS: false. */}
        <NextScript />
      </body>
    </Html>
  );
}
