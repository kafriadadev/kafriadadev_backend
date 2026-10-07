import { Head, Html, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en-NG">
      <Head>
        <link rel="icon" href="/brand/kafriada-net-mark.svg" />
        <link rel="manifest" href="/manifest.webmanifest" />
        <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
      </Head>
      <body>
        <Main />
        {/* Renders nothing on pages with unstable_runtimeJS: false. */}
        <NextScript />
      </body>
    </Html>
  );
}
