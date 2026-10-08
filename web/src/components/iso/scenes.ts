/*
 * The scenes behind the signed-in screens, the referee set for errors, and the
 * staff figures. Each takes the real state it shows; nothing here is invented.
 */
import { frame, g, type V3 } from "./kernel.ts";
import { cardFace, cardStanding, defs, floodlight, handRaised, person, phoneStanding, pitch, towerBounds, type Lamp } from "./kit.ts";
import { ball, booth, cash, dugout, plinth, printer, scoreboard, table, terminal, unplugged, wire, type BoothShows } from "./parts.ts";
import type { Figure } from "./figures.ts";

/* -- AUT-03: your ID is ready. A podium under three floodlights. ------------- */

/**
 * The stage the athlete's card stands on. The page sets the real card on it:
 * `lift` is how far down the figure the podium's top lies, as a fraction of
 * the figure's width (so a negative margin-top in % lines the two up), and
 * `shift` how far to move it sideways, in the same unit, to centre the podium.
 */
export function doneStage(): Figure & { lift: number; shift: number } {
  const W = 170, D = 124, R = 48;
  const K = frame([[0, 0, 0], [W, 0, 0], [0, D, 0], [W, D, 0], ...towerBounds(10, 8, 6, 54), ...towerBounds(W - 12, 6, 6, 54), ...towerBounds(6, D - 14, 6, 54)], { margin: 0.02 });
  let s = defs();
  s += pitch(K, 0, 0, W, D, 6, "pitch");
  const cx = W / 2, cy = D / 2 + 4;
  s += floodlight(K, 10, 8, 6, 54, true, { aim: [cx - 14, cy - 8], spread: 20, delay: 200 });
  s += floodlight(K, W - 12, 6, 6, 54, true, { aim: [cx + 8, cy - 14], spread: 20, delay: 450 });
  s += floodlight(K, 6, D - 14, 6, 54, true, { aim: [cx - 16, cy + 6], spread: 20, delay: 700 });
  // A round dais: its outline is an ellipse centred under the card at any width.
  s += `<circle class="iso-shade" transform="${K.TOP(cx + 3, cy + 3, 6)}" r="${R + 3}"/>`;
  s += K.cylinder(cx, cy, 6, R, 5);
  s += K.cylinder(cx, cy, 11, R - 7, 4, "iso-on");
  const [ax, ay] = K.P(cx, cy, 15);
  return { viewBox: K.viewBox, body: s, lift: ay / K.W, shift: 0.5 - ax / K.W };
}

/* -- ATH-01: your ground. Four floodlights, one per thing the athlete has. --- */

export type GroundState = { profile: Lamp; card: Lamp; photo: Lamp; club: Lamp };

/** Each tower carries `data-key`, so the list beside it can light it on hover (/iso.js). */
export function ground(st: GroundState): Figure {
  const W = 150, D = 100;
  const K = frame([[0, 0, 0], [W, 0, 0], [0, D, 0], [W, D, 0], ...towerBounds(4, 70, 5, 50), ...towerBounds(4, 26, 5, 50), ...towerBounds(46, 4, 5, 50), ...towerBounds(104, 4, 5, 50)], { margin: 0.03 });
  const cx = W / 2, cy = D / 2;
  const all = Object.values(st).every((v) => v === true);
  const tower = (key: keyof GroundState, x: number, y: number, aim: [number, number], i: number) =>
    g(floodlight(K, x, y, 5, 50, st[key], { aim, spread: 14, delay: 200 + i * 220 }), { "data-key": key });
  // Along the two back edges, so none hides the player. Left to right on screen: the list's order.
  let s = defs();
  s += pitch(K, 0, 0, W, D, 5, "pitch");
  s += tower("profile", 4, 70, [cx - 22, cy + 10], 0);
  s += tower("card", 4, 26, [cx - 12, cy - 4], 1);
  s += tower("photo", 46, 4, [cx - 2, cy - 10], 2);
  s += tower("club", 104, 4, [cx + 14, cy - 6], 3);
  s += g(person(K, cx + 6, cy + 8, 5, { kit: true, arms: all ? "up" : "down", scale: 1.2 }), { "data-a": "rise", style: "--d:100ms" });
  s += ball(K, cx + 22, cy + 20, 5, 3.8);
  return { viewBox: K.viewBox, body: s };
}

/* -- VER-01: the VAR booth. Card or cash, both lanes lead to the same check. - */

export type BoothState = "none" | "draft" | "under_review" | "approved" | "rejected" | "escalated" | "revoked";

export function varBooth(state: BoothState): Figure {
  const W = 156, D = 100;
  const K = frame([[0, 0, 0], [W, 0, 0], [0, D, 0], [W, D, 0], [61, 3, 52], [152, 40, 58]], { margin: 0.03 });
  const inFlight = state === "under_review" || state === "escalated";
  const fedIn = inFlight || state === "approved" || state === "rejected";
  const shows: BoothShows = inFlight ? "wait" : state === "approved" ? "done" : state === "rejected" ? "warn" : "off";
  let s = defs();
  s += pitch(K, 0, 0, W, D, 5, "edge");
  // Lane one, the card terminal, at the back left.
  s += wire(K, [[27, 27, 5.2], [27, 21, 5.2], [64, 21, 5.2]], fedIn, 0);
  s += terminal(K, 20, 12, 5, fedIn);
  // The booth, at the back.
  s += booth(K, 64, 6, 5, 34, 26, 42, shows);
  // Out of its side: the card, with the photo once it is approved.
  s += wire(K, [[98, 20, 5.2], [134, 20, 5.2], [134, 40, 5.2]], state === "approved", 600);
  // Lane two, cash at the coordinator's table, at the front left.
  s += wire(K, [[50, 72, 5.2], [80, 72, 5.2], [80, 32, 5.2]], fedIn, 250);
  s += person(K, 32, 58, 5, { kit: false, arms: "down" });
  s += table(K, 16, 64, 5, 32, 16, 14);
  s += cash(K, 24, 72, 19);
  s += plinth(K, 114, 40, 5, 40, 14, 6);
  s += g(cardStanding(K, 118, 44, 11, 32, 46, { lit: true, photo: state === "approved" }), state === "approved" ? { "data-a": "rise", style: "--d:900ms" } : {});
  return { viewBox: K.viewBox, body: s };
}

/* -- The referee set: errors and empty states. ------------------------------ */

/** 404: the ball has gone out over the touchline, and the flag is up. */
export function outOfPlay(): Figure {
  const K = frame([[0, 0, 0], [110, 0, 0], [0, 74, 0], [110, 74, 0], [60, 20, 56]], { margin: 0.04, aspect: 4 / 3 });
  let s = "";
  // Beyond the line: plain ground. Inside: the grass, its touchline along y = 44.
  s += K.box(0, 0, 0, 110, 44, 5, 0, "iso-grass");
  s += `<g transform="${K.TOP(0, 0, 5)}"><path class="iso-chalk" d="M0 40H110M18 40V0"/><circle class="iso-chalk" cx="18" cy="40" r="7" stroke-dasharray="0" /></g>`;
  s += K.box(0, 44, 0, 110, 30, 5, 0, "iso-out");
  s += person(K, 66, 30, 5, { kit: false, arms: "up", scale: 1.05 });
  // The flag in the raised near hand.
  const hx = 66 + 5.25 + 7.35, hz = 5 + 31.5 + 11.5;
  s += `<path class="iso-ln" style="stroke-width:1.6px" d="${K.path([[hx, 30, hz - 6], [hx, 30, hz + 10]])}"/>`;
  const fw = 12, fh = 8;
  s += g(`<g transform="${K.FRONT(hx, 30, hz + 10)}"><rect class="iso-warn-f" width="${fw}" height="${fh}"/><path class="iso-bad-f" d="M0 0H${fw / 2}V${fh / 2}H0ZM${fw / 2} ${fh / 2}H${fw}V${fh}H${fw / 2}Z"/><rect class="iso-ln" width="${fw}" height="${fh}"/></g>`, { "data-a": "wave", style: "--d:500ms" });
  s += g(ball(K, 40, 60, 5, 4.6), { "data-a": "roll", style: "--sx:-26px;--sy:-15px;--d:150ms" });
  return { viewBox: K.viewBox, body: s };
}

/** Offline: the phone has no signal and the floodlights are off. */
export function noSignal(): Figure {
  const K = frame([[0, 0, 0], [110, 0, 0], [0, 80, 0], [110, 80, 0], ...towerBounds(8, 8, 5, 46), ...towerBounds(96, 6, 5, 46)], { margin: 0.04, aspect: 4 / 3 });
  let s = pitch(K, 0, 0, 110, 80, 5, "pitch");
  s += floodlight(K, 8, 8, 5, 46, false);
  s += floodlight(K, 96, 6, 5, 46, false);
  s += phoneStanding(K, 66, 44, 5, "nosignal", false, 28, 52);
  return { viewBox: K.viewBox, body: s };
}

/** Our side is down: the scoreboard is dark and its cable lies unplugged. */
export function serverDown(): Figure {
  const K = frame([[0, 0, 0], [110, 0, 0], [0, 80, 0], [110, 80, 0], [28, 22, 44], [78, 22, 44]], { margin: 0.04, aspect: 4 / 3 });
  let s = pitch(K, 0, 0, 110, 80, 5, "edge");
  s += scoreboard(K, 28, 22, 5, "--:--", true);
  s += unplugged(K, [64, 26, 5.5], [70, 52, 5]);
  s += K.box(84, 46, 5, 9, 5, 7, 1);
  s += `<g transform="${K.FRONT(84, 51, 12)}"><rect class="iso-ink" x="2.6" y="2" width="1.4" height="3" rx=".5"/><rect class="iso-ink" x="5" y="2" width="1.4" height="3" rx=".5"/></g>`;
  return { viewBox: K.viewBox, body: s };
}

/** Something went wrong: the referee holds up a card. Yellow means try again; red means it cannot go ahead. */
export function heldCard(colour: "yellow" | "red"): Figure {
  const K = frame([[0, 0, 0], [80, 0, 0], [0, 60, 0], [80, 60, 0], [40, 26, 62]], { margin: 0.05, aspect: 4 / 3 });
  let s = pitch(K, 0, 0, 80, 60, 5, "edge");
  const x = 40, y = 30;
  s += person(K, x, y, 5, { kit: false, arms: "up", scale: 1.1 });
  const u = 1.1, hx = x + u * 5 + u * 7 + 0.6, hz = 5 + u * 30 + u * 11 + 1;
  const cls = colour === "yellow" ? "iso-warn-f" : "iso-bad-f";
  s += g(`<g transform="${K.FRONT(hx - 4, y + 0.5, hz + 13)}"><rect class="${cls}" width="9" height="13" rx="1"/><rect class="iso-ln" width="9" height="13" rx="1"/></g>`, { "data-a": "rise", style: "--d:300ms" });
  return { viewBox: K.viewBox, body: s };
}

/* -- ATH-05: not in a club yet. Hold up your ID; a seat is waiting. -------- */

/**
 * The athlete holds up his ID card; a lit path runs from him to the one open
 * seat in a club's dugout. What the words under it say: a club adds you by
 * your ID.
 */
export function noClub(): Figure {
  const W = 100, D = 76, seats = 6, open = 3;
  const dx = 34, dy = 6;
  const seatX = dx + 2.5 + 1.6 + open * (7 + 1.6) + 3.5;
  const px = 18, py = 58, sc = 1.15;
  const K = frame([[0, 0, 0], [W, 0, 0], [0, D, 0], [W, D, 0], [dx - 1.5, dy - 1.5, 31], [dx + 60, dy - 1.5, 31], [px, py, 5 + 41 * sc + 16]], { margin: 0.04, aspect: 16 / 10 });
  let s = defs();
  s += pitch(K, 0, 0, W, D, 5, "edge");
  s += dugout(K, dx, dy, 5, seats, 0, open);
  // The path: from where he stands, across the pitch, to the open seat.
  s += wire(K, [[px + 7, py, 5.2], [seatX, py, 5.2], [seatX, dy + 18, 5.2]], true, 700);
  s += g(person(K, px, py, 5, { kit: true, arms: "raise", scale: sc }), { "data-a": "rise", style: "--d:100ms" });
  const [hx, hy, hz] = handRaised(px, py, 5, sc);
  const cw = 12, ch = 17.4;
  s += g(`<g transform="${K.FRONT(hx - cw / 2, hy + 0.8, hz + ch - 3)}"><rect class="iso-paper-f" width="${cw}" height="${ch}" rx=".8"/>${cardFace(cw, ch, { lit: true })}<rect class="iso-ln" width="${cw}" height="${ch}" rx=".8"/></g>`, { "data-a": "rise", style: "--d:350ms" });
  return { viewBox: K.viewBox, body: s };
}

/** No invitations yet: the athlete's phone, its inbox empty and waiting. */
export function noInvitations(): Figure {
  const K = frame([[0, 0, 0], [80, 0, 0], [0, 56, 0], [80, 56, 0], [30, 24, 60]], { margin: 0.05, aspect: 16 / 10 });
  let s = pitch(K, 0, 0, 80, 56, 5, "edge");
  s += phoneStanding(K, 26, 24, 5, "inbox", true, 30, 54);
  return { viewBox: K.viewBox, body: s };
}

/* -- CLB-02: the dugout. One seat per player, lit as the squad fills. ------- */

export function squadBench(players: number, seats = 11): Figure {
  const filled = Math.min(players, seats);
  const w = seats * 8.6 + 6.6;
  const K = frame([[0, 0, 0], [w + 16, 0, 0], [0, 40, 0], [w + 16, 40, 0], [8, 6, 34]], { margin: 0.04 });
  let s = pitch(K, 0, 0, w + 16, 40, 4, "edge");
  s += dugout(K, 8, 6, 4, seats, filled);
  return { viewBox: K.viewBox, body: s };
}

/* -- CRD-06: the card printer. A sheet of eight, the ones to print lit. ----- */

export function cardPrinter(toPrint: number): Figure {
  const K = frame([[0, 0, 0], [96, 0, 0], [0, 110, 0], [96, 110, 0], [16, 6, 28], [80, 6, 28]], { margin: 0.03, aspect: 4 / 3 });
  let s = K.box(0, 0, 0, 96, 110, 4, 3);
  s += printer(K, 20, 8, 4, Math.min(8, toPrint));
  return { viewBox: K.viewBox, body: s };
}

/* -- ADM-05: rollout. One plot per LGA, a floodlight on each that is live. -- */

export type Plot = { key: string; live: boolean };

export function rollout(plots: Plot[], cols = 6): Figure {
  const size = 18, gap = 6, rows = Math.ceil(plots.length / cols);
  const W = cols * (size + gap) + gap, D = rows * (size + gap) + gap;
  const K = frame([[0, 0, 0], [W, 0, 0], [0, D, 0], [W, D, 0], [gap, gap, 30]], { margin: 0.03 });
  let s = defs();
  s += K.box(0, 0, 0, W, D, 4, 3);
  plots.forEach((p, i) => {
    const r = Math.floor(i / cols), c = i % cols;
    const x = gap + c * (size + gap), y = gap + r * (size + gap);
    let t = K.box(x, y, 4, size, size, p.live ? 4 : 2, 0, p.live ? "iso-grass" : "");
    const z = p.live ? 8 : 6;
    if (p.live) t += `<g transform="${K.TOP(x, y, z)}"><rect class="iso-chalk" x="2.5" y="2.5" width="${size - 5}" height="${size - 5}"/><path class="iso-chalk" d="M${size / 2} 2.5V${size - 2.5}"/></g>`;
    if (p.live) {
      // A floodlight on each live plot, at its back corner.
      t += K.box(x + 2, y + 2, z, 1.6, 1.6, 10);
      t += K.box(x + 0.6, y + 1.6, z + 10, 5, 2.4, 3.6, 0, "iso-on");
      const [hx, hy] = K.P(x + 3, y + 3, z + 12);
      t += `<circle class="iso-halo" cx="${hx}" cy="${hy}" r="6" filter="url(#iso-bloom)"/>`;
    }
    s += g(t, { "data-key": p.key, ...(p.live ? { "data-a": "light", style: `--d:${100 + i * 40}ms` } : {}) });
  });
  return { viewBox: K.viewBox, body: s };
}

export type { V3 };
