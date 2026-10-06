import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

import { getImage, getProfile } from "@/lib/api";
import messages from "../../../../messages/en.json";

export const runtime = "nodejs";

/*
 * The share preview for a public profile (1200 × 630): the player card, so a
 * link posted on WhatsApp shows the player, not a grey box. Drawn on the
 * server; colours are the plate tokens' values, because an image cannot read
 * CSS variables (tokens.css is the source).
 */
const PLATE = "#FFFFFF";
const INK = "#0A0F0B";
const MUTED = "#4B5A4F";
const PITCH = "#0EAD2C";
const RED = "#EB0002";

const fonts = (async () => {
  const dir = join(process.cwd(), "assets", "fonts");
  const [display, body, mono] = await Promise.all([
    readFile(join(dir, "FiraSansCondensed-ExtraBoldItalic.ttf")),
    readFile(join(dir, "Andika-Regular.ttf")),
    readFile(join(dir, "GeistMono-Medium.ttf")),
  ]);
  return [
    { name: "Display", data: display, weight: 800 as const, style: "italic" as const },
    { name: "Body", data: body, weight: 400 as const, style: "normal" as const },
    { name: "Mono", data: mono, weight: 500 as const, style: "normal" as const },
  ];
})();

const logo = readFile(join(process.cwd(), "public", "brand", "kafriada-net-horizontal.svg"), "utf8").then(
  (svg) => `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`,
);

export async function GET(_request: Request, { params }: { params: Promise<{ kuid: string }> }) {
  const { kuid } = await params;
  const profile = await getProfile(kuid).catch(() => null);
  if (!profile) return new Response("Not found", { status: 404 });

  let photo: string | null = null;
  if (profile.is_verified && profile.photo_url) {
    const res = await getImage(`/v1/public/athletes/${encodeURIComponent(kuid)}/photo`);
    if (res?.ok) photo = `data:image/jpeg;base64,${Buffer.from(await res.arrayBuffer()).toString("base64")}`;
  }

  const image = new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", background: PITCH, fontFamily: "Body" }}>
        {/* Chalk lines: halfway line and centre circle behind the card. */}
        <div style={{ position: "absolute", left: 0, top: 315, width: 1200, height: 3, background: "rgba(255,255,255,.35)" }} />
        <div style={{ position: "absolute", left: 420, top: 135, width: 360, height: 360, borderRadius: 999, border: "3px solid rgba(255,255,255,.35)" }} />
        <div
          style={{
            margin: 48, flex: 1, display: "flex", background: PLATE, borderRadius: 28, overflow: "hidden",
            boxShadow: "0 12px 40px rgba(0,0,0,.25)",
          }}
        >
          <div style={{ width: 340, display: "flex", alignItems: "center", justifyContent: "center", background: "#E6EAE4", borderRight: `10px solid ${RED}` }}>
            {photo ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={photo} width={340} height={534} style={{ objectFit: "cover" }} alt="" />
            ) : (
              <svg width="200" height="240" viewBox="0 0 80 96">
                <circle cx="40" cy="32" r="16" fill="#A3AEA6" />
                <path d="M8 96c0-22 14-36 32-36s32 14 32 36z" fill="#A3AEA6" />
              </svg>
            )}
          </div>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "40px 48px" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={await logo} width={173} height={56} style={{ alignSelf: "flex-start" }} alt="" />
            <div style={{ marginTop: 36, fontFamily: "Display", fontSize: 76, lineHeight: 0.95, color: INK, textTransform: "uppercase" }}>
              {profile.full_name}
            </div>
            <div style={{ marginTop: 18, fontSize: 32, color: MUTED, display: "flex" }}>
              {[profile.playing_position, `${profile.lga_name}, ${profile.state_name}`].filter(Boolean).join(" · ")}
            </div>
            {profile.is_verified ? (
              <div style={{ marginTop: 18, alignSelf: "flex-start", background: PITCH, color: INK, borderRadius: 999, padding: "6px 20px", fontSize: 26 }}>
                {messages.ui.verified}
              </div>
            ) : null}
            <div style={{ marginTop: "auto", background: INK, color: PLATE, borderRadius: 10, padding: "14px 22px", display: "flex", flexDirection: "column" }}>
              <div style={{ fontSize: 18, letterSpacing: 4, opacity: 0.85 }}>{messages.ui.idLabel.toUpperCase()}</div>
              <div style={{ fontFamily: "Mono", fontSize: 40 }}>{profile.kuid}</div>
            </div>
          </div>
        </div>
      </div>
    ),
    { width: 1200, height: 630, fonts: await fonts },
  );
  image.headers.set("cache-control", "public, max-age=300, s-maxage=300");
  return image;
}
