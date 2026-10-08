/*
 * Venue parts: the booth, the coordinator's table, the card terminal, cash,
 * a ball, the assistant referee's flag, a scoreboard, a dugout, a printer.
 */
import { g, type Kernel, type V3 } from "./kernel.ts";
import { digit, screen, shadow } from "./kit.ts";

const on = (lit: boolean | undefined) => (lit ? " iso-on" : "");

/** A wire along the ground (dashed when idle), with a travelling pulse when live. */
export function wire(K: Kernel, pts: V3[], live: boolean, delay = 0) {
  const d = K.path(pts);
  let s = `<path class="iso-wire${on(live)}" d="${d}"/>`;
  if (live) s += `<path class="iso-pulse" pathLength="100" d="${d}" style="--d:${delay}ms"/>`;
  return s;
}

export type BoothShows = "off" | "wait" | "done" | "warn";

/**
 * The VAR booth, where a reviewer checks the photo: a cabin with a wide screen
 * on its front and a door on its side.
 */
export function booth(K: Kernel, x: number, y: number, z: number, w: number, d: number, h: number, show: BoothShows) {
  let s = shadow(K, x, y, z, w, d, 4);
  s += K.box(x, y, z, w, d, h);
  s += K.box(x - 2.5, y - 2.5, z + h, w + 5, d + 5, 3.5);
  const sw = w - 8, sh = h * 0.5;
  const lit = show !== "off";
  let f = `<rect class="iso-ink" x="3" y="5" width="${w - 6}" height="${sh + 4}" rx="1.5"/>`;
  f += `<rect class="${show === "warn" ? "iso-glass" : `iso-glass${on(lit)}`}" x="4" y="6" width="${sw}" height="${sh + 2}" rx="1"/>`;
  if (show === "wait") {
    f += `<g transform="translate(4 6)">${screen(sw, sh + 2, "wait")}</g>`;
    f += `<rect class="iso-on-f iso-scan" x="4" y="${6 + (sh + 2) / 2}" width="${sw}" height="1.2" style="--sy0:${-(sh / 2)}px;--sy1:${sh / 2}px"/>`;
  } else if (show === "done") {
    f += `<g transform="translate(4 6)">${screen(sw, sh + 2, "check")}</g>`;
  } else if (show === "warn") {
    // A yellow card on the screen: fixable, not final.
    const cw = sh * 0.42, ch = sh * 0.62;
    f += `<rect class="iso-warn-f" x="${4 + sw / 2 - cw / 2}" y="${6 + (sh + 2 - ch) / 2}" width="${cw}" height="${ch}" rx="1" transform="rotate(12 ${4 + sw / 2} ${6 + (sh + 2) / 2})"/>`;
  }
  f += `<rect class="iso-d" x="3" y="${sh + 13}" width="${w - 6}" height="${h - sh - 17}" rx="1"/>`;
  f += `<circle class="${lit && show !== "warn" ? "iso-on-f" : "iso-lamp"}" cx="7" cy="${sh + 16.5}" r="1.3"/>`;
  f += `<circle class="${show === "warn" ? "iso-warn-f" : "iso-lamp"}" cx="11" cy="${sh + 16.5}" r="1.3"/>`;
  s += `<g transform="${K.FRONT(x, y + d, z + h)}">${f}</g>`;
  const dw = d * 0.42;
  s += `<g transform="${K.SIDE(x + w, y + d, z + h)}"><rect class="iso-s" x="${d * 0.3}" y="${h * 0.2}" width="${dw}" height="${h * 0.8}"/>` +
    `<rect class="iso-glass" x="${d * 0.3 + 2}" y="${h * 0.2 + 3}" width="${dw - 4}" height="${h * 0.22}"/>` +
    `<circle class="iso-ink-f" cx="${d * 0.3 + dw - 2.5}" cy="${h * 0.62}" r=".9"/></g>`;
  return s;
}

/** A card terminal (pay by card) on a short stand. */
export function terminal(K: Kernel, x: number, y: number, z: number, lit: boolean) {
  let s = shadow(K, x, y, z, 14, 12, 2);
  s += K.box(x + 4, y + 3, z, 6, 6, 12);
  s += K.box(x, y, z + 12, 14, 12, 4, 1.5);
  let top = `<rect class="iso-ink" x="2" y="1.5" width="10" height="4.5" rx="1"/>`;
  top += `<rect class="${lit ? "iso-on-f" : "iso-lamp"}" x="3" y="2.5" width="8" height="2.5" rx=".5"/>`;
  for (let r = 0; r < 2; r++) for (let c = 0; c < 3; c++) top += `<rect class="iso-d" x="${2.6 + c * 3.2}" y="${7.4 + r * 2.2}" width="2.4" height="1.5" rx=".4"/>`;
  s += `<g transform="${K.TOP(x, y, z + 16)}">${top}</g>`;
  // A bank card resting in the slot.
  s += K.box(x + 3, y + 11, z + 13, 8, 0.8, 7, 0, "iso-bank");
  return s;
}

/** A table, its top at z + h. */
export function table(K: Kernel, x: number, y: number, z: number, w: number, d: number, h = 14) {
  const l = 2.4;
  let s = shadow(K, x, y, z, w, d, 3);
  for (const [lx, ly] of [[x + 1, y + 1], [x + w - 1 - l, y + 1], [x + 1, y + d - 1 - l], [x + w - 1 - l, y + d - 1 - l]]) s += K.box(lx, ly, z, l, l, h - 2);
  s += K.box(x, y, z + h - 2, w, d, 2);
  return s;
}

/** A small stack of banknotes. */
export function cash(K: Kernel, x: number, y: number, z: number) {
  let s = "";
  for (let i = 0; i < 3; i++) s += K.box(x + i * 0.7, y - i * 0.5, z + i * 1.1, 15, 8, 1.1, 0, "iso-cash");
  s += `<g transform="${K.TOP(x + 1.4, y - 1, z + 3.3)}"><rect class="iso-cash-ink" x="1" y="1" width="13" height="6" rx=".6"/><circle class="iso-cash-ink" cx="7.5" cy="4" r="1.8"/></g>`;
  return s;
}

/** A football: a projected sphere with a few panel lines. */
export function ball(K: Kernel, x: number, y: number, z: number, r = 4) {
  const [cx, cy] = K.P(x, y, z + r);
  let s = `<circle class="iso-shade" transform="${K.TOP(x + r * 0.3, y + r * 0.3, z)}" r="${r}"/>`;
  s += `<circle class="iso-ball" cx="${cx}" cy="${cy}" r="${r}"/>`;
  const p = r * 0.42;
  const pts = [0, 1, 2, 3, 4].map((i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
    return [cx + p * Math.cos(a), cy + p * Math.sin(a)];
  });
  s += `<path class="iso-ink-f" d="M${pts.map((q) => q.map((v) => v.toFixed(2)).join(" ")).join("L")}Z"/>`;
  s += `<path class="iso-ball-seam" d="${pts.map(([px, py]) => {
    const dx = px - cx, dy = py - cy, k = (r * 0.92) / p;
    return `M${px.toFixed(2)} ${py.toFixed(2)}L${(cx + dx * k).toFixed(2)} ${(cy + dy * k).toFixed(2)}`;
  }).join("")}"/>`;
  return s;
}

/** The assistant referee's flag, raised: a pole and a chequered flag. */
export function flag(K: Kernel, x: number, y: number, z: number, h = 30) {
  let s = K.box(x, y, z, 1.8, 1.8, h, 0);
  const fw = 13, fh = 9;
  let f = `<rect class="iso-warn-f" width="${fw}" height="${fh}"/>`;
  f += `<path class="iso-bad-f" d="M0 0H${fw / 2}V${fh / 2}H0ZM${fw / 2} ${fh / 2}H${fw}V${fh}H${fw / 2}Z"/>`;
  f += `<rect class="iso-ln" width="${fw}" height="${fh}"/>`;
  s += g(`<g transform="${K.FRONT(x + 1.8, y + 1.8, z + h)}">${f}</g>`, { "data-a": "wave", style: "--d:500ms" });
  return s;
}

/** A scoreboard on two legs: digits lit, or dark when `off`. */
export function scoreboard(K: Kernel, x: number, y: number, z: number, text: string, off = false) {
  const w = 50, h = 22, t = 4, legH = 12;
  let s = shadow(K, x, y, z, w, t + 2, 3);
  s += K.box(x + 7, y + 0.5, z, 3, 3, legH);
  s += K.box(x + w - 10, y + 0.5, z, 3, 3, legH);
  s += K.box(x, y, z + legH, w, t, h);
  let f = `<rect class="iso-ink" x="2" y="2" width="${w - 4}" height="${h - 4}" rx="1"/>`;
  const dw = 6.4, dh = 11, gap = 2.8, total = text.length * dw + (text.length - 1) * gap;
  let cx = (w - total) / 2;
  for (const ch of text) {
    f += digit(ch, cx, (h - dh) / 2, dw, dh, off ? "iso-off-seg" : "iso-score-seg");
    cx += dw + gap;
  }
  s += `<g transform="${K.FRONT(x, y + t, z + legH + h)}">${f}</g>`;
  return s;
}

/**
 * A dugout: back wall, side panels and a roof over a row of seats; the first
 * `filled` are lit, and seat `open` (if given) is drawn as the one waiting.
 */
export function dugout(K: Kernel, x: number, y: number, z: number, seats: number, filled: number, open = -1) {
  const sw = 7, gap = 1.6, w = seats * (sw + gap) + gap + 5, d = 17, h = 24;
  let s = shadow(K, x, y, z, w, d, 3);
  s += K.box(x, y, z, w, 3, h);
  s += K.box(x, y, z, 2.5, d, h);
  for (let i = 0; i < seats; i++) {
    const sx = x + 2.5 + gap + i * (sw + gap);
    const cls = i < filled ? "iso-on" : i === open ? "iso-open" : "";
    const lit = i < filled || i === open;
    s += g(K.box(sx, y + 3.4, z + 0.5, sw, 1.6, 14, 0, cls) + K.box(sx + 0.8, y + 6.5, z, 1.2, 1.2, 4, 0) + K.box(sx + sw - 2, y + 6.5, z, 1.2, 1.2, 4, 0) + K.box(sx, y + 5, z + 4, sw, 5.5, 2, 0, cls), lit ? { "data-a": i === open ? "flicker" : "light", style: `--d:${150 + i * 90}ms` } : {});
  }
  s += K.box(x + w - 2.5, y, z, 2.5, d, h);
  s += K.box(x - 1.5, y - 1.5, z + h, w + 3, d + 4, 2.2, 0, "iso-roof");
  return s;
}

/** A desktop printer pushing out a sheet of eight cards; the first `lit` are highlighted. */
export function printer(K: Kernel, x: number, y: number, z: number, lit: number) {
  const w = 56, d = 34, h = 18;
  let s = shadow(K, x, y, z, w, d, 3);
  // The sheet first: it lies on the desk in front, under the printer's lip.
  const pw = w - 16, pd = 54, px = x + 8, py = y + d - 6;
  let sheet = K.box(px, py, z, pw, pd, 0.6, 0, "iso-paper");
  let face = "";
  const cw = (pw - 6) / 2, ch = (pd - 10) / 4;
  for (let r = 0; r < 4; r++) for (let c = 0; c < 2; c++) {
    const i = r * 2 + c, cx = 2 + c * (cw + 2), cy = 2 + r * (ch + 2);
    face += `<rect class="${i < lit ? "iso-plate-on" : "iso-plate-soft"}" x="${cx}" y="${cy}" width="${cw}" height="${ch}" rx="1"/>`;
    face += `<rect class="iso-plate-ink" x="${cx}" y="${cy + ch - 2.4}" width="${cw}" height="2.4"/>`;
    face += `<rect class="iso-paper-f" x="${cx + 1.5}" y="${cy + 2.2}" width="${cw * 0.3}" height="${ch * 0.42}" rx=".5"/>`;
  }
  sheet += `<g transform="${K.TOP(px, py, z + 0.6)}">${face}</g>`;
  s += K.box(x, y, z, w, d, h, 2);
  s += `<g transform="${K.TOP(x, y, z + h)}"><rect class="iso-d" x="4" y="4" width="${w - 8}" height="10" rx="1.5"/>` +
    `<rect class="iso-ink" x="${w - 17}" y="${d - 12}" width="12" height="7" rx="1"/><rect class="iso-on-f" x="${w - 15.5}" y="${d - 10.5}" width="5" height="4" rx=".5"/></g>`;
  s += `<g transform="${K.FRONT(x, y + d, z + h)}"><rect class="iso-ink" x="6" y="${h * 0.62}" width="${w - 12}" height="2.6" rx="1"/></g>`;
  s += g(sheet, { "data-a": "slide", style: "--sx:-10px;--sy:-6px;--d:250ms" });
  return s;
}

/** A plinth to stand something on. */
export const plinth = (K: Kernel, x: number, y: number, z: number, w: number, d: number, h = 6) => shadow(K, x, y, z, w, d, 3) + K.box(x, y, z, w, d, h, 2);

/** A wall socket and a cable whose plug lies apart from it (the service is down). */
export function unplugged(K: Kernel, from: V3, plugAt: V3) {
  const [x, y, z] = plugAt;
  let s = `<path class="iso-cable" d="${K.path([from, [from[0], from[1] + 8, z + 1], [x - 6, y, z + 1], [x, y, z + 1]])}"/>`;
  s += K.box(x, y - 1.6, z, 6, 3.2, 3.2, 0.8, "iso-ink");
  s += `<path class="iso-ln" d="${K.path([[x + 6, y - 0.8, z + 1.8], [x + 8.5, y - 0.8, z + 1.8]])}M${K.P(x + 6, y + 0.8, z + 1.8).join(" ")}L${K.P(x + 8.5, y + 0.8, z + 1.8).join(" ")}"/>`;
  return s;
}
