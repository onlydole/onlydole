// Type as geometry. Glyph outlines come from glyphs.js, so letters can be
// laid out, animated per character, warped point by point and, for the
// variable display face, morphed continuously along the width and weight axes.

import { FONTS } from "./glyphs.js";
import { clamp, hash } from "./lib.js";

class Face {
  constructor(data) {
    this.upm = data.upm;
    this.cap = data.cap;
    this.axes = data.axes;
    this.pairs = data.kern;
    this.raw = data.glyphs;
    this.cache = new Map();
  }

  glyph(ch) {
    let g = this.cache.get(ch);
    if (g) return g;
    const raw = this.raw[ch] ?? this.raw[" "];
    g = {
      cmds: raw.c,
      adv: raw.a.split(" ").map(Number),
      pts: raw.p.map((s) =>
        s ? Float32Array.from(s.split(" "), Number) : new Float32Array(0),
      ),
    };
    this.cache.set(ch, g);
    return g;
  }

  // Bilinear weights over the width x weight master grid.
  weights(wdth, wght) {
    if (!this.axes) return [[0, 1]];
    const seg = (v, stops) => {
      const x = clamp(v, stops[0], stops[stops.length - 1]);
      let i = 0;
      while (i < stops.length - 2 && x > stops[i + 1]) i++;
      return [i, (x - stops[i]) / (stops[i + 1] - stops[i])];
    };
    const [wi, wf] = seg(wdth, this.axes.wdth);
    const [gi, gf] = seg(wght, this.axes.wght);
    const n = this.axes.wdth.length;
    return [
      [gi * n + wi, (1 - wf) * (1 - gf)],
      [gi * n + wi + 1, wf * (1 - gf)],
      [(gi + 1) * n + wi, (1 - wf) * gf],
      [(gi + 1) * n + wi + 1, wf * gf],
    ].filter(([, w]) => w > 1e-6);
  }

  shape(ch, wdth = 100, wght = 900) {
    const g = this.glyph(ch);
    const ws = this.weights(wdth, wght);
    if (ws.length === 1) {
      const m = ws[0][0];
      return { cmds: g.cmds, pts: g.pts[m], adv: g.adv[m] };
    }
    const len = g.pts[0].length;
    const pts = new Float32Array(len);
    let adv = 0;
    for (const [m, w] of ws) {
      const src = g.pts[m];
      for (let i = 0; i < len; i++) pts[i] += src[i] * w;
      adv += g.adv[m] * w;
    }
    return { cmds: g.cmds, pts, adv };
  }

  kern(a, b) {
    return this.pairs[a + b] ?? 0;
  }
}

export const fonts = {
  display: new Face(FONTS.anybody),
  serif: new Face(FONTS.serif),
  italic: new Face(FONTS.serifItalic),
  mono: new Face(FONTS.mono),
};

export function layout(face, str, o) {
  const { size, wdth = 100, wght = 900, tracking = 0 } = o;
  const s = size / face.upm;
  const kernScale = face.axes ? wdth / 100 : 1;
  const items = [];
  let x = 0;
  let prev = null;
  for (const ch of str) {
    const sh = face.shape(ch, wdth, wght);
    if (prev) x += face.kern(prev, ch) * s * kernScale;
    items.push({ ch, sh, x, w: sh.adv * s });
    x += sh.adv * s + tracking * size;
    prev = ch;
  }
  const width = items.length ? x - tracking * size : 0;
  return { items, width, scale: s, cap: face.cap * s };
}

/** Width-axis value that sets `str` to exactly `target` pixels wide. */
export function fitWidth(face, str, target, size, wght = 900) {
  let lo = 50;
  let hi = 150;
  for (let i = 0; i < 28; i++) {
    const mid = (lo + hi) / 2;
    if (layout(face, str, { size, wdth: mid, wght }).width < target) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

function trace(ctx, sh, ox, oy, s, warp) {
  const p = sh.pts;
  const pt = [0, 0];
  const at = (i) => {
    pt[0] = ox + p[i] * s;
    pt[1] = oy - p[i + 1] * s;
    if (warp) warp(pt);
    return pt;
  };
  let k = 0;
  for (const c of sh.cmds) {
    if (c === "M") {
      at(k);
      ctx.moveTo(pt[0], pt[1]);
      k += 2;
    } else if (c === "L") {
      at(k);
      ctx.lineTo(pt[0], pt[1]);
      k += 2;
    } else if (c === "Q") {
      const [x1, y1] = at(k);
      at(k + 2);
      ctx.quadraticCurveTo(x1, y1, pt[0], pt[1]);
      k += 4;
    } else if (c === "C") {
      const [x1, y1] = at(k);
      const [x2, y2] = at(k + 2);
      at(k + 4);
      ctx.bezierCurveTo(x1, y1, x2, y2, pt[0], pt[1]);
      k += 6;
    } else {
      ctx.closePath();
    }
  }
}

/**
 * Draw a string as vector outlines.
 *
 * o.letter(i, item, L) may return { dx, dy, sx, sy, rot, alpha, hide, color }
 * to animate each glyph about its own centre; o.warp(pt) may move any outline
 * point in place.
 */
export function drawText(ctx, face, str, o) {
  const L = layout(face, str, o);
  const align = o.align ?? "left";
  let x0 = o.x;
  if (align === "center") x0 -= L.width / 2;
  else if (align === "right") x0 -= L.width;
  const baseAlpha = ctx.globalAlpha;
  for (let i = 0; i < L.items.length; i++) {
    const it = L.items[i];
    if (it.ch === " " || o.skip?.includes(i)) continue;
    const tr = o.letter ? o.letter(i, it, L) : null;
    if (tr?.hide) continue;
    const gx = x0 + it.x;
    ctx.save();
    if (tr) {
      const cx = gx + it.w / 2;
      const cy = o.y - L.cap / 2;
      ctx.translate(cx + (tr.dx ?? 0), cy + (tr.dy ?? 0));
      if (tr.rot) ctx.rotate(tr.rot);
      ctx.scale(tr.sx ?? 1, tr.sy ?? 1);
      ctx.translate(-cx, -cy);
      ctx.globalAlpha = baseAlpha * (tr.alpha ?? 1);
    }
    ctx.beginPath();
    trace(ctx, it.sh, gx, o.y, L.scale, o.warp);
    if (o.stroke) {
      ctx.lineWidth = o.lineWidth ?? 2;
      ctx.lineJoin = "round";
      ctx.strokeStyle = tr?.color ?? o.stroke;
      ctx.stroke();
    } else {
      ctx.fillStyle = tr?.color ?? o.color;
      ctx.fill();
    }
    ctx.restore();
  }
  L.x0 = x0;
  return L;
}

const GLITCH = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&/+:";

/**
 * Decode effect: characters resolve left to right behind a short band of
 * random glyphs. `p` runs 0..1, `step` changes the random glyphs.
 */
export function scramble(text, p, seed = 0, step = 0) {
  const band = 4;
  const head = p * (text.length + band);
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const at = head - i;
    if (ch === " " || at >= band) out += ch;
    else if (at > 0) {
      const r = hash(seed * 7919 + i * 104729 + step * 15485863);
      out += GLITCH[Math.floor(r * GLITCH.length)];
    } else out += " ";
  }
  return out;
}
