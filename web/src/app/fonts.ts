import localFont from "next/font/local";

/*
 * Self-hosted, cut to what KAFRIADA NET prints (scripts/design/subset_fonts.py).
 *
 * Each family is two faces: "latin", preloaded, and "extended" (Latin
 * Extended, carrying the Hausa letters Ɓ ɓ Ɗ ɗ Ƙ ƙ Ƴ ƴ and ʼ), declared with its
 * unicode-range so a phone downloads it only when a page uses one of those
 * letters. The extended face sits second in each font stack (tokens.css).
 *
 * Fira Sans Condensed and Andika were chosen because their files contain the
 * Hausa letters; the plan's Barlow Condensed and Atkinson Hyperlegible Next
 * do not (checked glyph by glyph, 2026-10-06). The ID font never needs them:
 * KUIDs, codes and references are A–Z and 0–9.
 */
// Ranges: latin U+0020-007E, U+00A0-00FF, U+2013-2014, U+2018-201A, U+201C-201E, U+2022, U+2026, U+20A6; extended U+0100-024F, U+02BC, U+1E00-1EFF.
// Written out in each call because the font loader accepts literals only.

export const display = localFont({
  src: [{ path: "../../assets/fonts/web/display-800i-latin.woff2", weight: "800", style: "italic" }],
  variable: "--font-display-face",
  display: "swap",
  declarations: [{ prop: "unicode-range", value: "U+0020-007E, U+00A0-00FF, U+2013-2014, U+2018-201A, U+201C-201E, U+2022, U+2026, U+20A6" }],
  // The stack order (latin, extended, system) is set in tokens.css.
  adjustFontFallback: false,
});

export const displayExtended = localFont({
  src: [{ path: "../../assets/fonts/web/display-800i-extended.woff2", weight: "800", style: "italic" }],
  variable: "--font-display-ext",
  display: "swap",
  preload: false,
  declarations: [{ prop: "unicode-range", value: "U+0100-024F, U+02BC, U+1E00-1EFF" }],
  adjustFontFallback: false,
});

export const body = localFont({
  src: [
    { path: "../../assets/fonts/web/body-400-latin.woff2", weight: "400", style: "normal" },
    { path: "../../assets/fonts/web/body-700-latin.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-body-face",
  display: "swap",
  declarations: [{ prop: "unicode-range", value: "U+0020-007E, U+00A0-00FF, U+2013-2014, U+2018-201A, U+201C-201E, U+2022, U+2026, U+20A6" }],
  // The stack order (latin, extended, system) is set in tokens.css.
  adjustFontFallback: false,
});

export const bodyExtended = localFont({
  src: [
    { path: "../../assets/fonts/web/body-400-extended.woff2", weight: "400", style: "normal" },
    { path: "../../assets/fonts/web/body-700-extended.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-body-ext",
  display: "swap",
  preload: false,
  declarations: [{ prop: "unicode-range", value: "U+0100-024F, U+02BC, U+1E00-1EFF" }],
  adjustFontFallback: false,
});

// Not preloaded: only pages that show an ID or a code download it. It holds
// A–Z, 0–9 and the separators an ID, code or phone number uses, nothing else.
export const mono = localFont({
  src: [{ path: "../../assets/fonts/web/mono-500-latin.woff2", weight: "500", style: "normal" }],
  variable: "--font-mono-face",
  display: "swap",
  preload: false,
  fallback: ["ui-monospace", "monospace"],
});

/** Every font variable, for the root element. */
export const fontVariables = [display, displayExtended, body, bodyExtended, mono].map((f) => f.variable).join(" ");

/**
 * The same variables as a :root rule, for the Pages Router, whose _document
 * cannot load fonts. The tokens resolve on :root, so the variables must be
 * there, not on a wrapper element.
 */
export const fontRootCss = `:root{${[
  ["--font-display-face", display],
  ["--font-display-ext", displayExtended],
  ["--font-body-face", body],
  ["--font-body-ext", bodyExtended],
  ["--font-mono-face", mono],
].map(([name, f]) => `${name as string}:${(f as typeof display).style.fontFamily}`).join(";")}}`;
