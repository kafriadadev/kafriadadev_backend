/*
 * The isometric drawing kernel: 3D points to SVG, nothing else.
 *
 * Ported from the iso-glow skill (MIT, April Zhu; after iso-figure by Tolga
 * Cohce). +x runs down-right, +y down-left, +z up. Only three faces of any box
 * are visible: the top, FRONT (the y = max face, lower left) and SIDE (the
 * x = max face, lower right). Each gets its own class, so the stylesheet can
 * shade them like daylight from the upper left. Paint order is the only depth
 * sort: draw back to front (smaller x + y first, lower z first).
 *
 * Every function returns an SVG string. Figures are drawn on the server and
 * reach the page as markup, so they work with JavaScript off.
 */

export type V3 = [number, number, number];

const C = Math.cos(Math.PI / 6);
const S = 0.5;
const n = (v: number) => +v.toFixed(1);
const m3 = (v: number) => +v.toFixed(3);

export type Kernel = ReturnType<typeof kernel>;

export function kernel(OX: number, OY: number) {
  const P = (x: number, y: number, z: number): [number, number] => [n((x - y) * C + OX), n((x + y) * S - z + OY)];
  const D = (x: number, y: number, z: number): [number, number] => [(x - y) * C, (x + y) * S - z];
  const plane = (o: V3, u: V3, v: V3) => {
    const [ox, oy] = P(...o), [ux, uy] = D(...u), [vx, vy] = D(...v);
    return `matrix(${m3(ux)} ${m3(uy)} ${m3(vx)} ${m3(vy)} ${ox} ${oy})`;
  };
  /** Face-local frames. Draw ordinary SVG inside `<g transform=…>`; local y grows downward on walls. */
  const TOP = (x: number, y: number, z: number) => plane([x, y, z], [1, 0, 0], [0, 1, 0]);
  const FRONT = (x: number, y: number, z: number) => plane([x, y, z], [1, 0, 0], [0, 0, -1]);
  const SIDE = (x: number, y: number, z: number) => plane([x, y, z], [0, -1, 0], [0, 0, -1]);

  const rect = (t: string, w: number, h: number, r = 0, cls = "iso-f") =>
    `<rect class="${cls}" transform="${t}" width="${n(w)}" height="${n(h)}"${r ? ` rx="${r}"` : ""}/>`;

  /** A 3D polyline as path data; `close` for a filled face. */
  const path = (pts: V3[], close = false) => "M" + pts.map((p) => P(...p).join(" ")).join("L") + (close ? "Z" : "");
  const poly = (pts: V3[], cls: string) => `<path class="${cls}" d="${path(pts, true)}"/>`;
  const line = (a: V3, b: V3, cls = "iso-d") => `<path class="${cls}" d="${path([a, b])}"/>`;

  /** Rounded box: one rounded top over one continuous wall, so corners meet cleanly. */
  const rounded = (x: number, y: number, z: number, w: number, d: number, h: number, r: number, cls: string) => {
    r = Math.min(r, w / 2, d / 2);
    const steps = Math.max(3, Math.min(14, Math.round(r * 1.5))), z1 = z + h, q = Math.PI / 4, H = Math.PI / 2;
    const arc = (cx: number, cy: number, a0: number, a1: number) => {
      const o: [number, number][] = [];
      for (let i = 0; i <= steps; i++) {
        const a = a0 + ((a1 - a0) * i) / steps;
        o.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
      }
      return o;
    };
    const ring = [...arc(x + w - r, y + r, -H, 0), ...arc(x + w - r, y + d - r, 0, H), ...arc(x + r, y + d - r, H, 2 * H), ...arc(x + r, y + r, 2 * H, 3 * H)];
    const vis = [...arc(x + w - r, y + r, -q, 0), ...arc(x + w - r, y + d - r, 0, H), ...arc(x + r, y + d - r, H, 3 * q)];
    const wall: V3[] = [...vis.map(([a, b]) => [a, b, z] as V3), ...vis.slice().reverse().map(([a, b]) => [a, b, z1] as V3)];
    const c = cls ? " " + cls : "";
    return `<path class="iso-f${c}" d="${path(wall, true)}"/><path class="iso-t${c}" d="${path(ring.map(([a, b]) => [a, b, z1] as V3), true)}"/>`;
  };

  /** A box as its three visible faces. `r` rounds the vertical edges; `cls` is added to every face. */
  const box = (x: number, y: number, z: number, w: number, d: number, h: number, r = 0, cls = "") => {
    if (r > 0) return rounded(x, y, z, w, d, h, r, cls);
    const c = cls ? " " + cls : "";
    return (
      poly([[x + w, y, z + h], [x + w, y + d, z + h], [x + w, y + d, z], [x + w, y, z]], "iso-s" + c) +
      poly([[x, y + d, z + h], [x + w, y + d, z + h], [x + w, y + d, z], [x, y + d, z]], "iso-f" + c) +
      poly([[x, y, z + h], [x + w, y, z + h], [x + w, y + d, z + h], [x, y + d, z + h]], "iso-t" + c)
    );
  };

  /** An upright cylinder (a rounded box whose radius is half its width). */
  const cylinder = (cx: number, cy: number, z: number, r: number, h: number, cls = "") => rounded(cx - r, cy - r, z, 2 * r, 2 * r, h, r, cls);

  /** A sphere projects to a circle of the same radius. */
  const sphere = (x: number, y: number, z: number, r: number, cls = "iso-t") => {
    const [cx, cy] = P(x, y, z);
    return `<circle class="${cls}" cx="${cx}" cy="${cy}" r="${r}"/>`;
  };

  /** A flat disc on the ground plane. */
  const disc = (cx: number, cy: number, z: number, r: number, cls = "iso-t") =>
    `<circle class="${cls}" transform="${TOP(cx, cy, z)}" r="${r}"/>`;

  return { P, D, plane, TOP, FRONT, SIDE, rect, path, poly, line, box, cylinder, sphere, disc };
}

/** Frame a scene from its extreme 3D corners. With `aspect`, the view box is padded to it. */
export function frame(points: V3[], { margin = 0.06, aspect }: { margin?: number; aspect?: number } = {}) {
  const d = points.map(([x, y, z]) => [(x - y) * C, (x + y) * S - z]);
  const x0 = Math.min(...d.map((p) => p[0])), x1 = Math.max(...d.map((p) => p[0]));
  const y0 = Math.min(...d.map((p) => p[1])), y1 = Math.max(...d.map((p) => p[1]));
  const m = margin * Math.max(x1 - x0, y1 - y0);
  let w = x1 - x0 + 2 * m, h = y1 - y0 + 2 * m;
  let ox = m - x0, oy = m - y0;
  if (aspect) {
    if (w / h < aspect) { const nw = h * aspect; ox += (nw - w) / 2; w = nw; }
    else { const nh = w / aspect; oy += (nh - h) / 2; h = nh; }
  }
  return { ...kernel(ox, oy), viewBox: `0 0 ${n(w)} ${n(h)}`, W: n(w), H: n(h) };
}

/** Parallel hairlines in a face-local frame, from a0 to a1, each spanning b0 → b1. */
export function slits(a0: number, a1: number, step: number, b0: number, b1: number, vertical = true, cls = "iso-d") {
  let s = "";
  for (let a = a0; a <= a1 + 1e-6; a += step) {
    const v = n(a);
    s += vertical ? `<path class="${cls}" d="M${v} ${b0}V${b1}"/>` : `<path class="${cls}" d="M${b0} ${v}H${b1}"/>`;
  }
  return s;
}

/** A group carrying a state hook: `data-part` names it for the stylesheet and /iso.js. */
export const g = (body: string, attrs: Record<string, string | number | undefined> = {}) => {
  const a = Object.entries(attrs).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => ` ${k}="${v}"`).join("");
  return `<g${a}>${body}</g>`;
};
