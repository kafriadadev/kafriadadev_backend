import { Andika, Fira_Sans_Condensed, Geist_Mono } from "next/font/google";

/*
 * Self-hosted at build time; the browser never calls Google.
 *
 * Only the Latin subset is preloaded. Latin Extended (which carries the Hausa
 * letters Ɓ ɓ Ɗ ɗ Ƙ ƙ Ƴ ƴ) is declared with its unicode-range, so a phone
 * downloads it only when a page actually uses one of those letters.
 *
 * Display and body were chosen because their font files contain those
 * letters; the plan's Barlow Condensed and Atkinson Hyperlegible Next do not
 * (checked glyph by glyph, 2026-10-06). The ID font never needs them: KUIDs,
 * codes and references are A–Z and 0–9.
 */
export const display = Fira_Sans_Condensed({
  // Italic only: every headline, name and big number is set like shirt lettering.
  weight: "800",
  style: "italic",
  subsets: ["latin"],
  variable: "--font-display-face",
  display: "swap",
});

export const body = Andika({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-body-face",
  display: "swap",
});

// Not preloaded: only pages that show an ID or a code download it.
export const mono = Geist_Mono({
  weight: "500",
  subsets: ["latin"],
  preload: false,
  variable: "--font-mono-face",
  display: "swap",
});
