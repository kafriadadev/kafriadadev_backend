/*
 * Every isometric figure on the site. A figure is a function from the state it
 * shows to { viewBox, body }; components/iso/Iso.tsx wraps it in an <svg>.
 * Draw order is depth order: back to front.
 */
import { frame, g, type V3 } from "./kernel.ts";
import { cardFlat, cardStanding, defs, floodlight, person, phoneFlat, phoneStanding, pitch, shadow, towerBounds } from "./kit.ts";
import { ball, booth, cash, dugout, flag, plinth, printer, scoreboard, table, terminal, unplugged, wire, type BoothShows } from "./parts.ts";

export type Figure = { viewBox: string; body: string };

/* -- Landing: how it works, three vignettes drawn to one scale --------------- */

// The same bounds for all three, so they sit side by side at one size.
const VIGNETTE: V3[] = [[0, 0, 0], [96, 0, 0], [0, 76, 0], [96, 76, 0], ...towerBounds(8, 6, 5, 46), ...towerBounds(84, 4, 5, 46)];

/** 1. Register free: a phone on the touchline, the form filled, its button lit. */
export function howRegister(): Figure {
  const K = frame(VIGNETTE, { aspect: 4 / 3, margin: 0.03 });
  let s = defs();
  s += pitch(K, 0, 0, 96, 76, 5, "edge");
  s += shadow(K, 30, 30, 5, 30, 4, 4);
  s += g(phoneStanding(K, 32, 28, 5, "form", true, 30, 58), { "data-a": "rise" });
  s += g(person(K, 20, 52, 5, { kit: true, arms: "reach", scale: 1.1 }), { "data-a": "rise", style: "--d:150ms" });
  return { viewBox: K.viewBox, body: s };
}

/** 2. Your ID: the card on a plinth, two floodlights switching on over it. */
export function howCard(): Figure {
  const K = frame(VIGNETTE, { aspect: 4 / 3, margin: 0.03 });
  let s = defs();
  s += pitch(K, 0, 0, 96, 76, 5, "pitch");
  s += floodlight(K, 8, 6, 5, 46, true, { aim: [42, 44], spread: 12, delay: 300 });
  s += floodlight(K, 84, 4, 5, 46, true, { aim: [52, 40], spread: 12, delay: 550 });
  s += shadow(K, 26, 34, 5, 44, 16, 3);
  s += K.box(26, 34, 5, 44, 16, 6, 2);
  s += g(cardStanding(K, 30, 40, 11, 36, 52, { lit: true }), { "data-a": "rise", style: "--d:100ms" });
  return { viewBox: K.viewBox, body: s };
}

/** 3. Get seen: a phone held over the card, the scan comes back green. */
export function howScan(): Figure {
  const K = frame(VIGNETTE, { aspect: 4 / 3, margin: 0.03 });
  let s = defs();
  s += pitch(K, 0, 0, 96, 76, 5, "edge");
  s += shadow(K, 20, 18, 5, 40, 58, 3);
  s += cardFlat(K, 20, 18, 5, 40, 58, { lit: true });
  // The scan: a column of light from the phone down to the QR (cardFace: x 25, y 28, 11.5 across).
  const qx = 45, qy = 46, q = 11.5;
  const z0 = 6.5, z1 = 38;
  const col = K.path([[qx, qy, z1], [qx + q, qy, z1], [qx + q, qy, z0], [qx + q, qy + q, z0], [qx, qy + q, z0], [qx, qy + q, z1]], true);
  s += g(`<path class="iso-beam iso-beam-strong" d="${col}"/>`, { "data-a": "fade", style: "--d:500ms" });
  s += `<rect class="iso-on-ln" transform="${K.TOP(qx - 1, qy - 1, z0)}" width="${q + 2}" height="${q + 2}" data-a="light" style="--d:700ms"/>`;
  s += g(phoneFlat(K, qx + q / 2 - 12, qy + q / 2 - 21, z1, "check", true, 24, 42), { "data-a": "drop", style: "--d:150ms" });
  return { viewBox: K.viewBox, body: s };
}

