/*
 * The shared parts every figure is built from: one world, drawn one way.
 * A pitch slab, the ID card, a phone, a floodlight, a person, a scoreboard.
 * Each takes a kernel (from frame()) and returns SVG markup.
 */
import { g, type Kernel, type V3 } from "./kernel.ts";

const on = (lit: boolean | undefined) => (lit ? " iso-on" : "");

/** A slab of grass with chalk markings. `marks`: "pitch" (halfway line and circle), "edge" (touchline only) or "none". */
export function pitch(K: Kernel, x: number, y: number, w: number, d: number, h = 5, marks: "pitch" | "edge" | "none" = "pitch") {
  let s = K.box(x, y, 0, w, d, h, 0, "iso-grass");
  if (marks === "none") return s;
  const i = Math.min(w, d) * 0.07;
  let m = `<rect class="iso-chalk" x="${i}" y="${i}" width="${w - 2 * i}" height="${d - 2 * i}"/>`;
  if (marks === "pitch") {
    const r = Math.min(w, d) * 0.16;
    m += `<path class="iso-chalk" d="M${w / 2} ${i}V${d - i}"/><circle class="iso-chalk" cx="${w / 2}" cy="${d / 2}" r="${r}"/>`;
    m += `<circle class="iso-chalk-f" cx="${w / 2}" cy="${d / 2}" r="1.2"/>`;
    const bw = d * 0.42, bd = w * 0.12;
    m += `<path class="iso-chalk" d="M${i} ${(d - bw) / 2}h${bd}v${bw}h${-bd}M${w - i} ${(d - bw) / 2}h${-bd}v${bw}h${bd}"/>`;
  }
  s += `<g transform="${K.TOP(x, y, h)}">${m}</g>`;
  return s;
}

/** A soft contact shadow on the ground, under an object of footprint w × d. */
export const shadow = (K: Kernel, x: number, y: number, z: number, w: number, d: number, grow = 3) =>
  K.poly([[x - grow, y + grow * 0.3, z], [x + w + grow * 0.6, y - grow * 0.2, z], [x + w + grow * 1.6, y + d + grow * 1.6, z], [x - grow * 0.2, y + d + grow * 1.6, z]], "iso-shade");

/** Deterministic QR-like pattern: three finder squares and a scatter that never changes between renders. */
function qr(x: number, y: number, size: number, cls = "iso-plate-ink") {
  const N = 9, c = size / N;
  let s = "";
  const finder = (fx: number, fy: number) =>
    `<rect class="${cls}" x="${x + fx * c}" y="${y + fy * c}" width="${3 * c}" height="${3 * c}"/>` +
    `<rect class="iso-paper-f" x="${x + fx * c + c * 0.6}" y="${y + fy * c + c * 0.6}" width="${c * 1.8}" height="${c * 1.8}"/>` +
    `<rect class="${cls}" x="${x + fx * c + c}" y="${y + fy * c + c}" width="${c}" height="${c}"/>`;
  s += finder(0, 0) + finder(N - 3, 0) + finder(0, N - 3);
  let seed = 7;
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
    const inFinder = (i < 3 && j < 3) || (i >= N - 3 && j < 3) || (i < 3 && j >= N - 3);
    seed = (seed * 37 + 11) % 101;
    if (!inFinder && seed % 3 !== 0) s += `<rect class="${cls}" x="${x + i * c}" y="${y + j * c}" width="${c * 0.92}" height="${c * 0.92}"/>`;
  }
  return s;
}

/**
 * The card's face, in a local frame of w × h (portrait). The same drawing goes
 * on a standing card (FRONT plane) or one lying flat (TOP plane).
 */
export function cardFace(w: number, h: number, { lit = true, photo = false }: { lit?: boolean; photo?: boolean } = {}) {
  const u = w / 40;
  let s = `<rect class="${lit ? "iso-plate-on" : "iso-plate-soft"}" width="${w}" height="${5.5 * u}"/>`;
  // Photo, or the silhouette an unverified card carries.
  s += `<rect class="iso-plate-soft" x="${3.5 * u}" y="${9 * u}" width="${13 * u}" height="${15 * u}" rx="${1 * u}"/>`;
  s += photo
    ? `<circle class="iso-plate-ink" cx="${10 * u}" cy="${14.5 * u}" r="${3.3 * u}"/><path class="iso-plate-ink" d="M${4.5 * u} ${24 * u}c0-5 2.5-6.6 ${5.5 * u}-6.6s${5.5 * u} 1.6 ${5.5 * u} 6.6z"/>`
    : `<circle class="iso-paper-f" cx="${10 * u}" cy="${14.5 * u}" r="${3.1 * u}"/><path class="iso-paper-f" d="M${5 * u} ${24 * u}c0-4.6 2.3-6.2 ${5 * u}-6.2s${5 * u} 1.6 ${5 * u} 6.2z"/>`;
  // Name, position, LGA.
  s += `<rect class="iso-plate-ink" x="${19.5 * u}" y="${10 * u}" width="${16 * u}" height="${2.6 * u}" rx="${0.6 * u}"/>`;
  s += `<rect class="iso-plate-ink" x="${19.5 * u}" y="${14.4 * u}" width="${11 * u}" height="${2.6 * u}" rx="${0.6 * u}"/>`;
  s += `<rect class="${lit ? "iso-plate-on" : "iso-plate-soft"}" x="${19.5 * u}" y="${19.5 * u}" width="${7 * u}" height="${4 * u}" rx="${2 * u}"/>`;
  // QR, bottom right.
  s += qr(25 * u, 28 * u, 11.5 * u);
  s += `<rect class="iso-plate-soft" x="${3.5 * u}" y="${29 * u}" width="${17 * u}" height="${1.6 * u}" rx="${0.8 * u}"/>`;
  s += `<rect class="iso-plate-soft" x="${3.5 * u}" y="${33 * u}" width="${12 * u}" height="${1.6 * u}" rx="${0.8 * u}"/>`;
  // The KUID strip along the foot.
  s += `<rect class="iso-plate-ink" y="${h - 9 * u}" width="${w}" height="${9 * u}"/>`;
  for (let i = 0; i < 9; i++) s += `<rect class="iso-paper-f" x="${(4 + i * 3.6) * u}" y="${h - 5.6 * u}" width="${2.4 * u}" height="${2.2 * u}" rx="${0.4 * u}"/>`;
  return s;
}

/** The ID card standing upright, its face toward the lower left. (x, y, z) is its back-bottom-left corner. */
export function cardStanding(K: Kernel, x: number, y: number, z: number, w = 40, h = 58, opts: { lit?: boolean; photo?: boolean } = {}) {
  const t = 1.6;
  return K.box(x, y, z, w, t, h, 0, "iso-paper") + `<g transform="${K.FRONT(x, y + t, z + h)}">${cardFace(w, h, opts)}</g>`;
}

/** The ID card lying flat, portrait along y. */
export function cardFlat(K: Kernel, x: number, y: number, z: number, w = 40, h = 58, opts: { lit?: boolean; photo?: boolean } = {}) {
  const t = 1.2;
  return K.box(x, y, z, w, h, t, 0, "iso-paper") + `<g transform="${K.TOP(x, y, z + t)}">${cardFace(w, h, opts)}</g>`;
}

export type Screen = "form" | "check" | "scan" | "off" | "wait" | "pay" | "nosignal" | "inbox";

/** What a phone or booth screen shows, in a local w × h frame. */
export function screen(w: number, h: number, kind: Screen) {
  const m = w * 0.14;
  switch (kind) {
    case "form": {
      let s = "";
      for (let i = 0; i < 3; i++) s += `<rect class="iso-ln" x="${m}" y="${h * 0.16 + i * h * 0.17}" width="${w - 2 * m}" height="${h * 0.1}" rx="1"/>`;
      s += `<rect class="iso-on-f" x="${m}" y="${h * 0.72}" width="${w - 2 * m}" height="${h * 0.13}" rx="${h * 0.065}"/>`;
      return s;
    }
    case "check": {
      const r = Math.min(w, h) * 0.3, cx = w / 2, cy = h * 0.42;
      return `<circle class="iso-on-f" cx="${cx}" cy="${cy}" r="${r}"/>` +
        `<path fill="none" stroke="var(--iso-glass-on)" stroke-width="2.5" d="M${cx - r * 0.45} ${cy}l${r * 0.32} ${r * 0.32}l${r * 0.6} ${-r * 0.62}"/>` +
        `<rect class="iso-on-f" x="${m}" y="${h * 0.78}" width="${w - 2 * m}" height="${h * 0.06}" rx="1" opacity=".5"/>`;
    }
    case "scan": {
      const a = Math.min(w, h) * 0.62, x0 = (w - a) / 2, y0 = (h - a) / 2, k = a * 0.24;
      return `<path class="iso-on-ln" d="M${x0} ${y0 + k}V${y0}H${x0 + k}M${x0 + a - k} ${y0}H${x0 + a}V${y0 + k}M${x0 + a} ${y0 + a - k}V${y0 + a}H${x0 + a - k}M${x0 + k} ${y0 + a}H${x0}V${y0 + a - k}"/>` +
        `<path class="iso-on-ln" d="M${x0 - 2} ${h / 2}H${x0 + a + 2}"/>`;
    }
    case "wait": {
      let s = "";
      for (let i = 0; i < 3; i++) s += `<circle class="iso-on-f" cx="${w / 2 + (i - 1) * w * 0.18}" cy="${h / 2}" r="${w * 0.055}" opacity="${0.4 + i * 0.3}"/>`;
      return s;
    }
    case "inbox": {
      // An empty envelope: nothing has arrived yet.
      const ew = w * 0.6, eh = ew * 0.66, ex = (w - ew) / 2, ey = h * 0.36;
      return `<rect class="iso-ln" x="${ex}" y="${ey}" width="${ew}" height="${eh}" rx="1.2"/>` +
        `<path class="iso-ln" d="M${ex} ${ey + 0.5}L${w / 2} ${ey + eh * 0.58}L${ex + ew} ${ey + 0.5}"/>` +
        `<rect class="iso-on-f" x="${ex}" y="${ey + eh + h * 0.08}" width="${ew}" height="${h * 0.05}" rx="1" opacity=".45"/>`;
    }
    case "pay": {
      return `<rect class="iso-ln" x="${m}" y="${h * 0.2}" width="${w - 2 * m}" height="${h * 0.3}" rx="2"/>` +
        `<rect class="iso-on-f" x="${m}" y="${h * 0.24}" width="${(w - 2 * m) * 0.3}" height="${h * 0.06}"/>` +
        `<rect class="iso-on-f" x="${m}" y="${h * 0.66}" width="${w - 2 * m}" height="${h * 0.13}" rx="${h * 0.065}"/>`;
    }
    case "nosignal": {
      let s = "";
      const bw = w * 0.12, base = h * 0.6;
      for (let i = 0; i < 4; i++) s += `<rect class="iso-ln" x="${w * 0.22 + i * bw * 1.5}" y="${base - (i + 1) * h * 0.07}" width="${bw}" height="${(i + 1) * h * 0.07}" rx=".6"/>`;
      s += `<path class="iso-bad-ln" d="M${w * 0.2} ${h * 0.28}L${w * 0.8} ${h * 0.66}"/>`;
      return s;
    }
    default:
      return "";
  }
}

/** A phone standing upright, screen toward the lower left. */
export function phoneStanding(K: Kernel, x: number, y: number, z: number, show: Screen, lit = true, w = 24, h = 46) {
  const t = 3;
  const sw = w - 4, sh = h - 9;
  return (
    K.box(x, y, z, w, t, h, 1.4) +
    `<g transform="${K.FRONT(x, y + t, z + h)}">` +
    `<rect class="iso-ink" x="1" y="1" width="${w - 2}" height="${h - 2}" rx="3"/>` +
    `<rect class="iso-glass${on(lit)}" x="2" y="4.5" width="${sw}" height="${sh}" rx="1.5"/>` +
    `<g transform="translate(2 4.5)">${lit || show === "nosignal" ? screen(sw, sh, show) : ""}</g>` +
    `<rect class="iso-paper-f" x="${w / 2 - 3}" y="${h - 3.2}" width="6" height="1.2" rx=".6" opacity=".5"/>` +
    `</g>`
  );
}

/** A phone lying flat (screen up), long side along y. */
export function phoneFlat(K: Kernel, x: number, y: number, z: number, show: Screen, lit = true, w = 26, h = 50) {
  const t = 3;
  return (
    K.box(x, y, z, w, h, t, 2) +
    `<g transform="${K.TOP(x, y, z + t)}">` +
    `<rect class="iso-ink" x="1" y="1" width="${w - 2}" height="${h - 2}" rx="3.5"/>` +
    `<rect class="iso-glass${on(lit)}" x="2.2" y="5" width="${w - 4.4}" height="${h - 10}" rx="1.5"/>` +
    `<g transform="translate(2.2 5)">${lit ? screen(w - 4.4, h - 10, show) : ""}</g>` +
    `</g>`
  );
}

/**
 * A floodlight tower: a lattice mast and a lamp head facing the lower left.
 * (x, y) is the mast's foot; `beam` sends light down toward +y over `reach`.
 */
/** The corners of a floodlight's head, for frame(): a tower at (x, y, z), H tall. */
export const towerBounds = (x: number, y: number, z: number, H: number): V3[] => [[x - 9, y - 1, z + H + 16], [x + 11, y - 1, z + H + 16], [x - 9, y + 3, z + H + 2]];

export type Lamp = boolean | "wait" | "warn";

export function floodlight(K: Kernel, x: number, y: number, z: number, H: number, state: Lamp, { aim = [x, y + 60] as [number, number], spread = 14, delay = 0, beam = true } = {}) {
  const mw = 3.2, hw = 20, hh = 13, hd = 3.4;
  const hx = x + mw / 2 - hw / 2, hz = z + H;
  let s = K.box(x - 1.5, y - 1.5, z, mw + 3, mw + 3, 2.5);
  s += K.box(x, y, z + 2.5, mw, mw, H - 2.5);
  // Lattice ties on the mast's front.
  let ties = "";
  for (let k = 6; k < H - 6; k += 7) ties += `<path class="iso-d" d="M0 ${k}L${mw} ${k + 3.5}"/>`;
  s += `<g transform="${K.FRONT(x, y + mw, z + H)}">${ties}</g>`;
  // The bracket and the head.
  s += K.box(hx + 2, y, hz, hw - 4, mw, 2);
  s += K.box(hx, y - 0.6, hz + 2, hw, hd, hh, 0);
  const lit = state === true;
  let lamps = "";
  const cols = 4, rows = 3, gx = (hw - 3) / cols, gy = (hh - 3) / rows;
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++)
    lamps += `<rect class="iso-lamp${state === "warn" ? " iso-lamp-warn" : on(lit || (state === "wait" && (r + c) % 2 === 0))}" x="${1.5 + c * gx + 0.5}" y="${1.5 + r * gy + 0.5}" width="${gx - 1}" height="${gy - 1}" rx=".8"/>`;
  s += `<g transform="${K.FRONT(hx, y - 0.6 + hd, hz + 2 + hh)}">${lamps}</g>`;
  if (lit && beam) {
    const fy = y - 0.6 + hd, top = hz + 2 + hh, bot = hz + 2;
    const [ax, ay] = aim;
    const beamPoly = K.path([[hx, fy, top], [hx + hw, fy, top], [hx + hw, fy, bot], [ax + spread, ay + spread * 0.5, 0.5], [ax - spread, ay - spread * 0.5, 0.5], [hx, fy, bot]], true);
    const halo = K.P(hx + hw / 2, fy, (top + bot) / 2);
    const pool = `<ellipse class="iso-beam" transform="${K.TOP(ax, ay, 0.5)}" rx="${spread * 1.25}" ry="${spread * 0.9}"/>`;
    s += g(`<path class="iso-beam" d="${beamPoly}"/>${pool}`, { "data-a": "fade", style: `--d:${delay + 250}ms` });
    s += `<circle class="iso-halo" cx="${halo[0]}" cy="${halo[1]}" r="${hw * 0.75}" filter="url(#iso-bloom)" data-a="fade" style="--d:${delay}ms"/>`;
  }
  return g(s, state ? { "data-a": "flicker", style: `--d:${delay}ms` } : {});
}

/**
 * A person facing the viewer: tube limbs (an outlined stroke), a rounded torso,
 * a round head. `kit` lights the shirt green (the athlete); otherwise the shirt
 * is neutral (a scout, an official). `arms`: "down", "up" (the logo's
 * celebration), "reach" (the near arm toward something at its side) or
 * "raise" (the near arm up, holding something out; see handRaised).
 */
export function person(K: Kernel, x: number, y: number, z: number, { kit = false, scale = 1, arms = "down" }: { kit?: boolean; scale?: number; arms?: "down" | "up" | "reach" | "raise" } = {}) {
  const u = scale;
  const bw = 10 * u, bd = 6 * u, legH = 15 * u, shortsH = 5 * u, bodyH = 13 * u;
  const bx = x - bw / 2, by = y - bd / 2;
  const hip = z + legH, waist = hip + shortsH - 1 * u, shoulder = waist + bodyH - 2 * u;
  const shirt = kit ? "on" : "plain";
  const tube = (a: V3, b: V3, w: number, cls: string) => {
    const d = K.path([a, b]);
    return `<path class="iso-tube-o" d="${d}" style="stroke-width:${w + 0.9}"/><path class="iso-tube iso-tube-${cls}" d="${d}" style="stroke-width:${w}"/>`;
  };
  const arm = (side: -1 | 1, kind: "down" | "up" | "reach") => {
    const sx = x + side * (bw / 2 + 0.6 * u), s0: V3 = [sx, y, shoulder];
    const hand: V3 =
      kind === "up" ? [x + side * (bw / 2 + 7 * u), y, shoulder + 11 * u]
      : kind === "reach" ? [x + side * (bw / 2 + 4 * u), y + 9 * u, shoulder + 2 * u]
      : [x + side * (bw / 2 + 2 * u), y + 0.5 * u, shoulder - 12 * u];
    const elbow: V3 = [s0[0] + (hand[0] - s0[0]) * 0.36, s0[1] + (hand[1] - s0[1]) * 0.36, s0[2] + (hand[2] - s0[2]) * 0.36];
    return tube(s0, hand, 3 * u, "skin") + tube(s0, elbow, 3.6 * u, shirt);
  };
  const near = arms === "raise" ? "up" : arms;
  let s = shadow(K, bx, by, z, bw, bd, 2.5 * u);
  s += tube([x - 2.3 * u, y, hip], [x - 2.6 * u, y + 0.4 * u, z + 1.2 * u], 3.2 * u, "skin");
  s += tube([x + 2.3 * u, y, hip], [x + 2.6 * u, y + 0.4 * u, z + 1.2 * u], 3.2 * u, "skin");
  s += K.box(bx + 0.4 * u, by + 0.3 * u, hip - 1 * u, bw - 0.8 * u, bd - 0.6 * u, shortsH, 1.6 * u, "iso-ink");
  s += arm(-1, arms === "reach" || arms === "raise" ? "down" : arms);
  s += K.box(bx, by, waist, bw, bd, bodyH, 2.6 * u, kit ? "iso-on" : "");
  s += K.cylinder(x, y, shoulder, 1.8 * u, 2.2 * u, "iso-skin");
  s += K.sphere(x, y, shoulder + 2.2 * u + 4.6 * u, 4.8 * u, "iso-t iso-skin");
  s += arm(1, near);
  return s;
}

/** A seven-segment digit in a local frame of w × h. */
const SEG: Record<string, string> = {
  "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgecd", "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", " ": "",
};
export function digit(ch: string, x: number, y: number, w: number, h: number, cls = "iso-on-f") {
  const t = w * 0.2, half = h / 2;
  const segs: Record<string, [number, number, number, number]> = {
    a: [t, 0, w - 2 * t, t], b: [w - t, t, t, half - 1.5 * t], c: [w - t, half + t / 2, t, half - 1.5 * t],
    d: [t, h - t, w - 2 * t, t], e: [0, half + t / 2, t, half - 1.5 * t], f: [0, t, t, half - 1.5 * t], g: [t, half - t / 2, w - 2 * t, t],
  };
  return (SEG[ch] ?? "").split("").map((k) => {
    const [a, b, c, d] = segs[k];
    return `<rect class="${cls}" x="${x + a}" y="${y + b}" width="${c}" height="${d}" rx="${t * 0.3}"/>`;
  }).join("");
}

/** Glow filter for the halos. One per figure, its id unique to that figure. */
export const defs = () =>
  `<defs><filter id="iso-bloom" filterUnits="userSpaceOnUse" x="-2000" y="-2000" width="6000" height="6000"><feGaussianBlur stdDeviation="9"/></filter></defs>`;

export type { V3 };

/** Where person(..., { arms: "raise" }) holds its near hand: x, y, z of the fist. */
export const handRaised = (x: number, y: number, z: number, scale = 1): V3 => [x + scale * 12, y, z + scale * 41];
