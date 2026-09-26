// The reel. One coral dot carries through eight chapters, each a different
// motion technique, each cut on the beat. drawFrame(ctx, t) paints the 2D
// layer for time t and returns the compositor settings for that instant.

import {
  clamp,
  ease,
  GOLDEN,
  hash,
  lerp,
  mixRGB,
  norm,
  PALETTE as P,
  pulse,
  rgb,
  rng,
  spring,
  TAU,
  tween,
} from "./lib.js";
import {
  B,
  BAR_COUNT,
  BAR_DELAY,
  BARS,
  BEAT,
  BOUNCES,
  CHAPTERS,
  DOT_HOP,
  DOT_LAND,
  END_LAND,
  END_WINK,
  FPS,
  H,
  LINE_DRAW,
  W,
} from "./timeline.js";
import { drawText, fitWidth, fonts, layout, scramble } from "./type.js";

const INK = rgb(P.ink);
const PAPER = rgb(P.paper);
const CORAL = rgb(P.coral);
const BLUE = rgb(P.blue);
const CX = W / 2;
const CY = H / 2;
const DOT_R = 36;

function fillAll(ctx, color) {
  ctx.fillStyle = color;
  ctx.fillRect(-W, -H, W * 3, H * 3);
}

function disc(ctx, x, y, r, color) {
  if (r <= 0) return;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, TAU);
  ctx.fillStyle = color;
  ctx.fill();
}

/** A ball with squash (sx, sy) and an optional stretch along `angle`. */
function blob(ctx, x, y, r, sx, sy, color, stretch = 0, angle = 0) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(sx, sy);
  if (stretch > 0.001) {
    ctx.rotate(angle);
    ctx.scale(1 + stretch, 1 / (1 + stretch));
  }
  disc(ctx, 0, 0, r, color);
  ctx.restore();
}

/** Damped jiggle after an impact at `t0`. Positive values squash. */
const jiggle = (t, t0, amp, freq = 6, decay = 12) =>
  t < t0
    ? 0
    : amp * Math.exp(-(t - t0) * decay) * Math.cos((t - t0) * TAU * freq);

function mono(ctx, text, x, y, color, o = {}) {
  return drawText(ctx, fonts.mono, text, {
    x,
    y,
    size: o.size ?? 15,
    wght: 500,
    tracking: o.tracking ?? 0.12,
    align: o.align,
    color,
  });
}

/* ------------------------------------------------------------------ */
/* 01 Squash & stretch                                                */
/* ------------------------------------------------------------------ */

const bounce = (() => {
  const FLOOR = 770;
  const yF = FLOOR - DOT_R;
  const I = BOUNCES;
  const T1 = I[1] - I[0];
  const g = (8 * 380) / (T1 * T1);
  const t0 = I[0] - Math.sqrt((2 * (yF + 90)) / g);
  const X0 = 470;
  const span = I[4] - t0;

  const state = (t) => {
    const u = norm(t, t0, I[4]);
    const x = lerp(X0, CX, ease.outCubic(u));
    const vx = t > t0 && t < I[4] ? ((CX - X0) * 3 * (1 - u) ** 2) / span : 0;
    if (t < I[0]) {
      const d = I[0] - t;
      return { x, y: yF - 0.5 * g * d * d, vx, vy: g * d };
    }
    if (t < I[4]) {
      let k = 0;
      while (t >= I[k + 1]) k++;
      const T = I[k + 1] - I[k];
      const tau = t - I[k];
      return {
        x,
        y: yF - 0.5 * g * tau * (T - tau),
        vx,
        vy: -0.5 * g * (T - 2 * tau),
      };
    }
    return { x, y: yF, vx: 0, vy: 0 };
  };

  const speeds = I.map((ti, k) =>
    k === 0 ? g * (ti - t0) : 0.5 * g * (ti - I[k - 1]),
  );
  const squash = (t) =>
    I.reduce(
      (d, ti, k) => d + jiggle(t, ti, clamp(speeds[k] / 5200) * 0.55, 6, 12),
      0,
    );

  // The motion path, sampled at even arc length like an After Effects trail.
  const path = [];
  let acc = 0;
  let prev = state(t0);
  for (let tt = t0; tt <= I[4]; tt += 1 / 600) {
    const s = state(tt);
    acc += Math.hypot(s.x - prev.x, s.y - prev.y);
    prev = s;
    if (acc >= 16) {
      acc = 0;
      path.push({ t: tt, x: s.x, y: s.y });
    }
  }

  // Keyframes at every contact and every apex.
  const keys = [];
  for (let k = 0; k < I.length; k++) {
    keys.push({ ...state(I[k]), t: I[k] });
    if (k < I.length - 1) {
      const tm = (I[k] + I[k + 1]) / 2;
      keys.push({ ...state(tm), t: tm });
    }
  }

  return { FLOOR, yF, t0, state, squash, path, keys };
})();

function diamond(ctx, x, y, s, alpha) {
  if (s <= 0) return;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(Math.PI / 4);
  ctx.fillStyle = INK;
  ctx.fillRect(-s / 2, -s / 2, s, s);
  ctx.strokeStyle = rgb(P.paper, 0.9 * alpha);
  ctx.lineWidth = 1.5;
  ctx.strokeRect(-s / 2, -s / 2, s, s);
  ctx.restore();
}

function drawBall(ctx, t) {
  if (t < bounce.t0) return;
  const s = bounce.state(t);
  let { x, y } = s;
  const d = bounce.squash(t);
  let sx = 1 + d * 0.8;
  let sy = 1 - d;
  const near = clamp(1 - (bounce.yF - y) / 60);
  let st = Math.min(0.3, Math.hypot(s.vx, s.vy) / 9000) * (1 - near * 0.85);
  const angle = Math.atan2(s.vy, s.vx);
  let r = DOT_R;
  let grounded = true;

  // Anticipation: sink, hold, tremble.
  const a = tween(t, BOUNCES[4] + 0.02, B(3.55));
  if (a > 0) {
    sx *= 1 + 0.5 * a;
    sy *= 1 - 0.42 * a;
    x += Math.sin(t * 113) * 2.4 * a * a;
  }
  // Release: launch to centre and swell until the dot is the whole frame.
  if (t >= B(3.55)) {
    const tl = norm(t, B(3.55), B(3.82));
    const rel = spring(t - B(3.55), 3.4, 0.35);
    const stretch = 1 + 0.7 * Math.sin(Math.PI * tl);
    sy = lerp(0.58, 1, rel) * stretch;
    sx = lerp(1.5, 1, rel) / stretch;
    y = lerp(bounce.yF + DOT_R * 0.42, CY, ease.outCubic(tl));
    grounded = false;
    st = 0;
    const tg = norm(t, B(3.7), B(4));
    r = DOT_R * (1 + 34 * ease.inExpo(tg));
    sx = lerp(sx, 1, tg);
    sy = lerp(sy, 1, tg);
  }
  if (grounded) y += DOT_R * (1 - sy) * near;
  blob(ctx, x, y, r, sx, sy, CORAL, st, angle);
}

function scene1(ctx, t, fx, hud) {
  fillAll(ctx, INK);
  fx.bloom = 0.55;
  hud.color = P.paper;
  const { FLOOR, yF } = bounce;

  // Floor with a ruler, drawn out from the centre.
  const out = tween(t, B(3.4), B(3.75), ease.inExpo);
  const fw = 1500 * tween(t, 0.1, 0.75, ease.outExpo) * (1 - out);
  if (fw > 1) {
    ctx.fillStyle = rgb(P.paper, 0.22);
    ctx.fillRect(CX - fw / 2, FLOOR, fw, 2);
    for (let x = -720; x <= 720; x += 40) {
      if (Math.abs(x) > fw / 2) continue;
      const major = x % 200 === 0;
      ctx.fillStyle = rgb(P.paper, major ? 0.24 : 0.1);
      ctx.fillRect(CX + x - 0.75, FLOOR + 10, 1.5, major ? 12 : 6);
    }
  }

  // Motion path and keyframes trail the ball.
  const fade = 1 - tween(t, B(3.05), B(3.5));
  if (fade > 0) {
    for (const s of bounce.path) {
      if (s.t > t) break;
      const pop = 1 + 1.6 * pulse(t - s.t, 18);
      disc(ctx, s.x, s.y, 2.1 * pop, rgb(P.paper, 0.34 * fade));
    }
    for (const k of bounce.keys) {
      if (k.t <= t) diamond(ctx, k.x, k.y, spring(t - k.t, 4, 0.38) * 8, fade);
    }
  }

  // Contact ripples and dust.
  const amps = [1, 0.75, 0.5, 0.32, 0.4];
  for (let k = 0; k < BOUNCES.length; k++) {
    const dt = t - BOUNCES[k];
    if (dt < 0 || dt > 0.6) continue;
    const amp = amps[k];
    const p = ease.outCubic(dt / 0.6);
    const x = bounce.state(BOUNCES[k]).x;
    const rx = 40 + 190 * p * amp;
    ctx.strokeStyle = rgb(P.paper, (1 - p) * 0.55 * amp);
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.ellipse(x, FLOOR, rx, rx * 0.14, 0, 0, TAU);
    ctx.stroke();
    for (let j = 0; j < 8; j++) {
      const r1 = hash(k * 97 + j * 13);
      const r2 = hash(k * 57 + j * 7 + 3);
      const dir = j % 2 ? 1 : -1;
      const dx = dir * (140 + 260 * r1) * amp * dt;
      const dy = -(120 + 280 * r2) * amp * dt + 800 * dt * dt;
      if (dy > 4) continue;
      disc(
        ctx,
        x + dx + dir * 30,
        FLOOR + dy - 2,
        1.5 + 2 * r2,
        rgb(P.paper, (1 - dt / 0.6) * 0.8),
      );
    }
  }

  // Warm light pooling on the floor under the ball.
  const s = bounce.state(t);
  if (t > bounce.t0 && t < B(3.6)) {
    const prox = clamp(1 - (yF - s.y) / 420) * (1 - out);
    const gr = ctx.createRadialGradient(s.x, FLOOR, 0, s.x, FLOOR, 170);
    gr.addColorStop(0, rgb(P.coral, 0.4 * prox));
    gr.addColorStop(1, rgb(P.coral, 0));
    ctx.save();
    ctx.translate(s.x, FLOOR);
    ctx.scale(1, 0.16);
    ctx.translate(-s.x, -FLOOR);
    ctx.fillStyle = gr;
    ctx.fillRect(s.x - 170, FLOOR - 170, 340, 340);
    ctx.restore();
  }

  drawBall(ctx, t);
}

/* ------------------------------------------------------------------ */
/* 02 Kinetic type                                                    */
/* ------------------------------------------------------------------ */

const poster = (() => {
  const face = fonts.display;
  const SIZE = 332;
  const LEFT = 140;
  const RIGHT = 1780;
  const BASE = [370, 652, 934];
  const LINES = ["ONE DOT.", "FIFTEEN", "SECONDS."];
  // Every line is justified to the same measure by solving for the width axis.
  const WD = LINES.map((s) => fitWidth(face, s, RIGHT - LEFT, SIZE));
  const dotAt = (line) => {
    const L = layout(face, LINES[line], { size: SIZE, wdth: WD[line] });
    const it = L.items[L.items.length - 1];
    return [LEFT + it.x + it.w / 2, BASE[line] - DOT_R];
  };
  const INTRO = 640;
  const introW = fitWidth(face, "ONE", 1480, INTRO);
  const intro = layout(face, "ONE", { size: INTRO, wdth: introW });
  return {
    face,
    SIZE,
    LEFT,
    RIGHT,
    BASE,
    LINES,
    WD,
    dot1: dotAt(0),
    dot3: dotAt(2),
    INTRO,
    introW,
    introWidth: intro.width,
    introCap: intro.cap,
  };
})();

function axisNote(ctx, t, line, wdth, t0) {
  const a = tween(t, t0, t0 + 0.3);
  if (a <= 0) return;
  const { LEFT, RIGHT, BASE } = poster;
  const y = BASE[line];
  const len = (RIGHT - LEFT) * ease.outExpo(a);
  ctx.fillStyle = rgb(P.ink, 0.28);
  ctx.fillRect(LEFT, y + 14, len, 2);
  const v = String(Math.round(wdth)).padStart(3, "0");
  mono(ctx, `WDTH ${v} · WGHT 900`, RIGHT, y + 42, rgb(P.ink, 0.62 * a), {
    size: 14,
    align: "right",
  });
}

function scene2(ctx, t, fx, hud) {
  const { face, SIZE, LEFT, BASE, WD, INTRO, introW } = poster;
  fillAll(ctx, CORAL);
  hud.color = P.ink;
  fx.bloom = 0.12;
  fx.vignette = 0.16;

  // Camera: slow push, beat punches, then a dive into the full stop.
  const zoom = tween(t, B(7.62), B(8), ease.inExpo);
  const focus = ease.outCubic(norm(t, B(7.62), B(8)));
  const drift =
    1 +
    0.018 * norm(t, B(5), B(7.6)) +
    0.014 * (pulse(t - B(6), 9) + pulse(t - B(7), 9));
  const sc = drift * (1 + 60 * zoom);
  const [d3x, d3y] = poster.dot3;
  ctx.save();
  ctx.translate(CX, CY);
  ctx.scale(sc, sc);
  ctx.translate(-lerp(CX, d3x, focus), -lerp(CY, d3y, focus));

  // "ONE": springs in huge, then slides up into line one while its width
  // axis narrows to fit the line.
  const m = tween(t, B(4.45), B(4.95), ease.inOutExpo);
  const oneW = lerp(introW, WD[0], m);
  drawText(ctx, face, "ONE", {
    x: lerp(CX - poster.introWidth / 2, LEFT, m),
    y: lerp(CY + poster.introCap / 2, BASE[0], m),
    size: lerp(INTRO, SIZE, m),
    wdth: oneW,
    color: INK,
    letter: (i) => {
      const s = spring(t - B(4) - [0.07, 0, 0.07][i], 2.3, 0.4);
      return { sx: s, sy: s, rot: (1 - s) * (i - 1) * 0.35 };
    },
  });
  axisNote(ctx, t, 0, oneW, B(4.5));

  // "DOT" drops in letter by letter.
  drawText(ctx, face, "ONE DOT.", {
    x: LEFT,
    y: BASE[0],
    size: SIZE,
    wdth: WD[0],
    color: INK,
    skip: [0, 1, 2, 3, 7],
    letter: (i) => {
      const s = spring(t - (B(5) - 0.16) - 0.045 * (i - 4), 2.4, 0.5);
      return s <= 0 ? { hide: true } : { dy: -900 * (1 - s) };
    },
  });

  // "FIFTEEN" rises through a mask while its width axis opens up.
  if (t > B(6) - 0.08) {
    const w2 = lerp(
      50,
      WD[1],
      tween(t, B(6) - 0.04, B(6) + 0.45, ease.outExpo),
    );
    ctx.save();
    ctx.beginPath();
    ctx.rect(LEFT - 60, BASE[1] - 250, 1800, 262);
    ctx.clip();
    drawText(ctx, face, "FIFTEEN", {
      x: LEFT,
      y: BASE[1],
      size: SIZE,
      wdth: w2,
      color: INK,
      letter: (i) => {
        const p = tween(
          t,
          B(6) - 0.06 + 0.028 * i,
          B(6) + 0.3 + 0.028 * i,
          ease.outExpo,
        );
        return { dy: 270 * (1 - p) };
      },
    });
    ctx.restore();
    axisNote(ctx, t, 1, w2, B(6));
  }

  // "SECONDS" flips up, one letter at a time.
  drawText(ctx, face, "SECONDS.", {
    x: LEFT,
    y: BASE[2],
    size: SIZE,
    wdth: WD[2],
    color: INK,
    skip: [7],
    letter: (i) => {
      const s = spring(t - (B(7) - 0.07) - 0.03 * i, 2.8, 0.42);
      if (s <= 0) return { hide: true };
      return { sy: s, dy: (i % 2 ? 1 : -1) * 40 * (1 - Math.min(1, s)) };
    },
  });
  if (t > B(7) - 0.08) axisNote(ctx, t, 2, WD[2], B(7));

  // The dot: drops onto line one, then hops down to punctuate line three.
  const [d1x, d1y] = poster.dot1;
  if (t >= DOT_HOP[0]) {
    const p = norm(t, DOT_HOP[0], DOT_HOP[1]);
    const x = lerp(d1x, d3x, p);
    const y = lerp(d1y, d3y, p) - 4 * 220 * p * (1 - p);
    const vx = d3x - d1x;
    const vy = d3y - d1y - 4 * 220 * (1 - 2 * p);
    const d = jiggle(t, DOT_HOP[1], 0.5, 5.5, 11);
    const st = p < 1 ? 0.35 * Math.sin(Math.PI * p) : 0;
    const ground = p >= 1 ? DOT_R * d : 0;
    blob(
      ctx,
      x,
      y + ground,
      DOT_R,
      1 + 0.8 * d,
      1 - d,
      PAPER,
      st,
      Math.atan2(vy, vx),
    );
  } else if (t >= DOT_LAND - 0.3) {
    const g = (2 * (d1y + 80)) / 0.09;
    const y = t < DOT_LAND ? d1y - 0.5 * g * (DOT_LAND - t) ** 2 : d1y;
    const pre = tween(t, DOT_HOP[0] - 0.14, DOT_HOP[0]);
    const d = jiggle(t, DOT_LAND, 0.5, 5.5, 11) + 0.2 * pre;
    const falling =
      t < DOT_LAND ? Math.min(0.3, (g * (DOT_LAND - t)) / 9000) : 0;
    blob(
      ctx,
      d1x,
      y + DOT_R * d,
      DOT_R,
      1 + 0.8 * d,
      1 - d,
      PAPER,
      falling,
      Math.PI / 2,
    );
  }

  ctx.restore();
}

/* ------------------------------------------------------------------ */
/* 03 Pattern & stagger                                               */
/* ------------------------------------------------------------------ */

const field = (() => {
  const COLS = 23;
  const ROWS = 11;
  const SP = 72;
  const dots = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const x = CX + (c - (COLS - 1) / 2) * SP;
      const y = CY + (r - (ROWS - 1) / 2) * SP;
      dots.push({
        x,
        y,
        d: Math.hypot(x - CX, y - CY),
        a: Math.atan2(y - CY, x - CX),
      });
    }
  }
  dots.sort((p, q) => p.d - q.d || p.a - q.a);
  const N = dots.length;
  const DMAX = dots[N - 1].d;
  const RMAX = 28 * Math.sqrt(N);
  dots.forEach((p, k) => {
    p.k = k;
    p.rr = 28 * Math.sqrt(k + 0.5);
    p.th = k * GOLDEN;
    p.tone = k % 21 === 0 ? P.blue : k % 13 === 0 ? P.coral : P.ink;
  });
  return { dots, N, DMAX, RMAX };
})();

function scene3(ctx, t, fx, hud) {
  fillAll(ctx, PAPER);
  hud.color = P.ink;
  fx.bloom = 0.1;
  fx.vignette = 0.08;
  const { dots, N, DMAX, RMAX } = field;
  const lt = t - B(8);
  const waves = [B(9)];
  const spin = Math.max(0, t - B(9.5));

  for (const p of dots) {
    // Emanate from the centre, staggered by distance.
    const delay = 0.05 + (p.d / DMAX) * 0.3;
    const e = ease.outBack(norm(lt, delay, delay + 0.34), 1.4);
    if (e <= 0) continue;
    let x = CX + (p.x - CX) * e;
    let y = CY + (p.y - CY) * e;
    let r = 7 * clamp(e * 2) * (1 + 0.1 * Math.sin(t * 4 - p.d * 0.015));
    let color = P.ink;

    // Radial shock waves on the beat.
    for (const w of waves) {
      if (t < w) continue;
      const front = (t - w) * 1500;
      const bump =
        Math.exp(-(((p.d - front) / 85) ** 2)) * Math.exp(-(t - w) * 0.8);
      if (bump < 0.002) continue;
      const push = bump * 18;
      x += Math.cos(p.a) * push;
      y += Math.sin(p.a) * push;
      r *= 1 + 1.4 * bump;
      color = mixRGB(color, P.coral, Math.min(1, bump * 1.4));
    }

    // Regrid into a sunflower: every dot takes its golden-angle seat.
    const mk = tween(
      t,
      B(9.5) + (p.k / N) * 0.2,
      B(9.5) + 0.42 + (p.k / N) * 0.2,
    );
    if (mk > 0) {
      const breathe = 1 + 0.05 * (pulse(t - B(10), 6) + pulse(t - B(11), 6));
      const th = p.th + spin * 0.9;
      const c = norm(t, B(11.5) + (1 - p.rr / RMAX) * 0.06, B(11.95));
      const suck = ease.inBack(c, 2.2);
      const rr = p.rr * breathe * (1 - suck);
      const swirl = th + suck * 2.5;
      const sx = CX + rr * Math.cos(swirl);
      const sy = CY + rr * Math.sin(swirl);
      x = lerp(x, sx, mk);
      y = lerp(y, sy, mk);
      r = lerp(r, 3 + 7.5 * (p.rr / RMAX), mk) * (1 - 0.6 * clamp(c));
      color = mixRGB(color, p.tone, mk);
    }
    disc(ctx, x, y, r, rgb(color));
  }

  // The seed dot, and the dot everything collapses back into.
  disc(ctx, CX, CY, 10 * spring(lt, 3.5, 0.4) * (1 - norm(lt, 0.3, 0.45)), INK);
  disc(ctx, CX, CY, 40 * spring(t - B(11.8), 3, 0.5), CORAL);
}

/* ------------------------------------------------------------------ */
/* 04 Liquid                                                          */
/* ------------------------------------------------------------------ */

const goo = (() => {
  const r = rng(7);
  const balls = Array.from({ length: 9 }, (_, i) => ({
    rx: 170 + 330 * r(),
    ry: 0,
    sp: (0.55 + 0.7 * r()) * (i % 2 ? 1 : -1),
    ph: r() * TAU,
    rad: 58 + 52 * r(),
    wob: r() * TAU,
  }));
  for (const b of balls) b.ry = b.rx * (0.45 + 0.25 * r());
  const sum = Math.sqrt(balls.reduce((a, b) => a + b.rad ** 2, 0));
  return { balls, sum };
})();

function gooBalls(t) {
  const lt = t - B(12);
  const burst = spring(lt, 1.6, 0.55);
  const conv = tween(t, B(15), B(15.9));
  const beat = pulse(t % BEAT, 9) * (1 - conv);
  const seed = 40 / Math.sqrt(goo.balls.length);
  return goo.balls.map((b) => {
    const th = b.ph + b.sp * lt * 1.3;
    let x = CX + b.rx * burst * Math.cos(th);
    let y = CY + b.ry * burst * Math.sin(th * 1.25 + b.wob);
    let rad = lerp(seed, b.rad, clamp(burst * 1.4)) * (1 + 0.12 * beat);
    x = lerp(x, CX, conv);
    y = lerp(y, CY, conv);
    rad = lerp(rad, (b.rad * 280) / goo.sum, conv);
    return [x, y, rad];
  });
}

function scene4(ctx, t, fx, hud, lite) {
  hud.color = P.paper;
  fx.bloom = 0.3;
  const balls = gooBalls(t);
  if (lite) {
    fillAll(ctx, BLUE);
    for (const [x, y, r] of balls) disc(ctx, x, y, r, CORAL);
    return;
  }
  fx.bg = P.blue;
  fx.balls = balls;
  fx.lit = [1.0, 0.56, 0.4];
  fx.shade = [0.55, 0.1, 0.16];
  fx.rim = [1.0, 0.74, 0.96];

  // Orbit guides and satellites, drawn on over the goo.
  const on = tween(t, B(12.15), B(12.9), ease.outCubic);
  const off = 1 - tween(t, B(15), B(15.6));
  ctx.save();
  ctx.translate(CX, CY);
  ctx.rotate(-0.22);
  ctx.setLineDash([2, 11]);
  ctx.lineWidth = 1.5;
  [260, 420, 600].forEach((rx, i) => {
    ctx.strokeStyle = rgb(P.paper, 0.22 * off);
    ctx.beginPath();
    ctx.ellipse(0, 0, rx, rx * 0.42, 0, 0, TAU * on);
    ctx.stroke();
    for (let j = 0; j < 4; j++) {
      const a =
        (j / 4) * TAU + (t - B(12)) * (0.9 - i * 0.2) * (i % 2 ? -1 : 1);
      disc(
        ctx,
        rx * Math.cos(a),
        rx * 0.42 * Math.sin(a),
        4 * on,
        rgb(P.paper, 0.85 * off),
      );
    }
  });
  ctx.restore();
}

/* ------------------------------------------------------------------ */
/* 05 Dimension                                                       */
/* ------------------------------------------------------------------ */

const SCALE = 280;

function knotPoint(s01, a) {
  const c = (q) => {
    const k = 2 + Math.cos(3 * q);
    return [
      (k * Math.cos(2 * q)) / 3,
      (k * Math.sin(2 * q)) / 3,
      Math.sin(3 * q) / 3,
    ];
  };
  const s = s01 * TAU;
  const h = 1e-3;
  const p = c(s);
  const p1 = c(s + h);
  const p0 = c(s - h);
  const T = p1.map((v, i) => v - p0[i]);
  const tl = Math.hypot(...T);
  for (let i = 0; i < 3; i++) T[i] /= tl;
  const A = p1.map((v, i) => v - 2 * p[i] + p0[i]);
  const dot = A[0] * T[0] + A[1] * T[1] + A[2] * T[2];
  const Nv = A.map((v, i) => v - dot * T[i]);
  const nl = Math.hypot(...Nv);
  for (let i = 0; i < 3; i++) Nv[i] /= nl;
  const Bv = [
    T[1] * Nv[2] - T[2] * Nv[1],
    T[2] * Nv[0] - T[0] * Nv[2],
    T[0] * Nv[1] - T[1] * Nv[0],
  ];
  const tube = 0.1;
  return p.map(
    (v, i) => (v + tube * (Math.cos(a) * Nv[i] + Math.sin(a) * Bv[i])) * 1.12,
  );
}

const cloud = (() => {
  const N = 1400;
  const pts = [];
  for (let i = 0; i < N; i++) {
    const y = 1 - (2 * (i + 0.5)) / N;
    const r = Math.sqrt(1 - y * y);
    const ph = i * GOLDEN;
    const u = ((i % 56) / 56) * TAU;
    const v = (Math.floor(i / 56) / 25) * TAU;
    const R = 0.95;
    pts.push({
      sphere: [r * Math.cos(ph), y, r * Math.sin(ph)],
      torus: [
        (1 + 0.42 * Math.cos(v)) * Math.cos(u) * R,
        0.42 * Math.sin(v) * R,
        (1 + 0.42 * Math.cos(v)) * Math.sin(u) * R,
      ],
      knot: knotPoint(i / N, i * 2.39996),
      lineX: lerp(-600, 600, i / (N - 1)),
      accent: i % 11 === 0,
      d1: ((1 - y) / 2) * 0.12,
      d2: (i / N) * 0.12,
      // The knot unspools into the line in curve order, left to right.
      d3: (i / N) * 0.22,
    });
  }
  return { N, pts, order: new Uint16Array(N), z: new Float32Array(N) };
})();

function rotate([x, y, z], yaw, pitch) {
  const cy = Math.cos(yaw);
  const sy = Math.sin(yaw);
  const X = x * cy + z * sy;
  const Z0 = -x * sy + z * cy;
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  return [X, y * cp - Z0 * sp, y * sp + Z0 * cp];
}

const orient = (t) => {
  const lt = t - B(16);
  return [lt * 1.15 + 0.3, 0.38 + 0.15 * Math.sin(lt * 1.4)];
};

function gizmo(ctx, t, alpha) {
  if (alpha <= 0) return;
  const [yaw, pitch] = orient(t);
  const ox = 120;
  const oy = 930;
  const axes = [
    [[1, 0, 0], P.coral, "X"],
    [[0, 1, 0], P.paper, "Y"],
    [[0, 0, 1], [125, 134, 255], "Z"],
  ];
  ctx.lineWidth = 2;
  for (const [v, col, name] of axes) {
    const [X, Y] = rotate(v, yaw, pitch);
    ctx.strokeStyle = rgb(col, alpha);
    ctx.beginPath();
    ctx.moveTo(ox, oy);
    ctx.lineTo(ox + X * 34, oy - Y * 34);
    ctx.stroke();
    mono(ctx, name, ox + X * 46, oy - Y * 46 + 5, rgb(col, alpha), {
      size: 12,
      align: "center",
    });
  }
  disc(ctx, ox, oy, 3, rgb(P.paper, alpha));
}

function scene5(ctx, t, fx, hud, lite) {
  fillAll(ctx, INK);
  hud.color = P.paper;
  fx.bloom = 0.7;
  const { N, pts, order, z } = cloud;
  const lt = t - B(16);
  const [yaw, pitch] = orient(t);
  const pop =
    1 + 0.2 * Math.sin(Math.min(1, lt / 0.35) * Math.PI) * Math.exp(-lt * 2);
  const band = lerp(1.2, -1.2, norm(lt, B(0.35), B(1.25)));
  const lineY = 800;
  const D = 3.4;
  const stride = lite ? 3 : 1;

  const sx = new Float32Array(N);
  const sy = new Float32Array(N);
  const rad = new Float32Array(N);
  const alpha = new Float32Array(N);
  const glow = new Float32Array(N);
  let n = 0;
  for (let i = 0; i < N; i += stride) {
    const p = pts[i];
    const a = tween(t, B(16.9) + p.d1, B(16.9) + p.d1 + 0.3);
    const b = tween(t, B(17.9) + p.d2, B(17.9) + p.d2 + 0.3);
    const c = tween(t, B(18.85) + p.d3, B(18.85) + p.d3 + 0.25);
    const pos = [0, 1, 2].map(
      (k) => lerp(lerp(p.sphere[k], p.torus[k], a), p.knot[k], b) * pop,
    );
    const [X, Y, Z] = rotate(pos, yaw, pitch);
    const persp = D / (D + Z);
    const blur = Math.min(6, Math.abs(Z) * 3.2) * (1 - c);
    sx[i] = lerp(CX + X * SCALE * persp, CX + p.lineX, c);
    sy[i] = lerp(CY - Y * SCALE * persp, lineY, c);
    rad[i] = lerp(2.7 * persp + blur * 0.6, 2.6, c);
    alpha[i] = lerp(
      (0.3 + (0.7 * clamp(persp - 0.62, 0, 0.6)) / 0.6) / (1 + blur * 0.45),
      1,
      c,
    );
    glow[i] = Math.exp(-(((p.sphere[1] - band) / 0.09) ** 2)) * (1 - a);
    z[i] = Z * (1 - c);
    order[n++] = i;
  }
  const idx = order.subarray(0, n).sort((i, j) => z[j] - z[i]);
  for (const i of idx) {
    const g = glow[i];
    const col = pts[i].accent || g > 0.5 ? CORAL : PAPER;
    ctx.globalAlpha = clamp(alpha[i] + g);
    disc(ctx, sx[i], sy[i], rad[i] * (1 + g * 1.4), col);
  }
  ctx.globalAlpha = 1;

  if (!lite) {
    const c = tween(t, B(18.85), B(19.4));
    gizmo(ctx, t, 0.85 * tween(t, B(16.1), B(16.5)) * (1 - c));
  }
}

/* ------------------------------------------------------------------ */
/* 06 Data                                                            */
/* ------------------------------------------------------------------ */

const chart = (() => {
  const X0 = 360;
  const X1 = 1560;
  const BASE = 800;
  const MAXH = 440;
  const step = (X1 - X0) / BAR_COUNT;
  const xs = BARS.map((_, k) => X0 + step * (k + 0.5));
  const tops = BARS.map((h, k) => [xs[k], BASE - h * MAXH]);
  // Catmull-Rom through the bar tops.
  const SEG = 16;
  const curve = [];
  for (let k = 0; k < tops.length - 1; k++) {
    const p0 = tops[Math.max(0, k - 1)];
    const p1 = tops[k];
    const p2 = tops[k + 1];
    const p3 = tops[Math.min(tops.length - 1, k + 2)];
    for (let s = 0; s < SEG; s++) {
      const u = s / SEG;
      const u2 = u * u;
      const u3 = u2 * u;
      curve.push(
        [0, 1].map(
          (i) =>
            0.5 *
            (2 * p1[i] +
              (-p0[i] + p2[i]) * u +
              (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * u2 +
              (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * u3),
        ),
      );
    }
  }
  curve.push(tops[tops.length - 1]);
  const M = curve.length - 1;
  const RING = [CX, 560];
  const RR = 230;
  return { X0, X1, BASE, MAXH, xs, tops, curve, M, SEG, RING, RR };
})();

/** Odometer: each digit column rolls, lower columns carry the higher ones. */
function odometer(ctx, value, digits, x, y, size, color) {
  const face = fonts.display;
  const dw = layout(face, "0", { size, wdth: 100 }).width * 1.02;
  const cap = (face.cap / face.upm) * size;
  const row = cap * 1.5;
  let started = false;
  for (let i = 0; i < digits; i++) {
    const place = 10 ** (digits - 1 - i);
    const d = Math.floor(value / place) % 10;
    const lower = value % place;
    const frac = place === 1 ? value % 1 : clamp(lower - (place - 1));
    if (!started && d === 0 && frac === 0 && i < digits - 1) continue;
    started = true;
    const cx = x + i * dw;
    ctx.save();
    ctx.beginPath();
    ctx.rect(cx - 4, y - cap - 12, dw + 8, cap + 24);
    ctx.clip();
    drawText(ctx, face, String(d), {
      x: cx,
      y: y - frac * row,
      size,
      wdth: 100,
      color,
    });
    drawText(ctx, face, String((d + 1) % 10), {
      x: cx,
      y: y + (1 - frac) * row,
      size,
      wdth: 100,
      color,
    });
    ctx.restore();
  }
}

function stats(ctx, t) {
  const items = [
    ["FRAMES", 900, 3, B(20.1), B(21.6)],
    ["BEATS", 32, 2, B(20.2), B(21.3)],
    ["DOT", 1, 1, B(20.35), B(20.4)],
  ];
  let x = chart.X0;
  for (const [label, target, digits, t0, t1] of items) {
    const a = tween(t, t0 - 0.1, t0 + 0.15);
    if (a > 0) {
      const v = target * ease.outExpo(norm(t, t0, t1));
      ctx.globalAlpha = a;
      odometer(ctx, v, digits, x, 250, 116, INK);
      mono(ctx, label, x + 2, 286, rgb(P.ink, 0.6), {
        size: 14,
        tracking: 0.2,
      });
      ctx.globalAlpha = 1;
    }
    x += digits * 82 + 90;
  }
}

function scene6(ctx, t, fx, hud) {
  fillAll(ctx, PAPER);
  hud.color = P.ink;
  fx.bloom = 0.1;
  fx.vignette = 0.08;
  const { X0, X1, BASE, MAXH, xs, curve, M, SEG, RING, RR } = chart;

  stats(ctx, t);

  // Axis and quiet gridlines, which fold away as the ring forms.
  const fold = 1 - tween(t, B(22), B(22.4), ease.inOutExpo);
  if (fold > 0) {
    const half = ((X1 - X0) / 2) * fold;
    for (let k = 1; k <= 4; k++) {
      ctx.fillStyle = rgb(P.ink, 0.07);
      ctx.fillRect(CX - half, BASE - (MAXH / 4) * k, half * 2, 1);
    }
    ctx.fillStyle = INK;
    ctx.fillRect(CX - half, BASE, half * 2, 2);
  }

  // Bars rise on springs, then collapse into dots at their tops.
  const ringAt = (j, spin) => {
    const a = -Math.PI / 2 + (j / M) * TAU + spin;
    return [RING[0] + RR * Math.cos(a), RING[1] + RR * Math.sin(a)];
  };
  const spin = 4 * ease.inCubic(norm(t, B(22.4), B(24.6)));
  const morph = (j) =>
    tween(t, B(22) + (0.15 * j) / M, B(22) + 0.45 + (0.15 * j) / M);
  const pts = curve.map((p, j) => {
    const m = morph(j);
    if (m <= 0) return p;
    const r = ringAt(j, spin);
    return [lerp(p[0], r[0], m), lerp(p[1], r[1], m)];
  });

  for (let k = 0; k < BAR_COUNT; k++) {
    const h = BARS[k] * MAXH * spring(t - BAR_DELAY(k), 2.3, 0.5);
    if (h <= 0.5) continue;
    const c = tween(t, B(21) + 0.02 * k, B(21) + 0.02 * k + 0.3);
    const [px, py] = c >= 1 ? pts[k * SEG] : [xs[k], BASE - h];
    const w = lerp(38, 22, c);
    const bottom = lerp(BASE, py + w, c);
    const hide = tween(t, B(22.6), B(22.9));
    if (hide >= 1) continue;
    ctx.fillStyle = k === BAR_COUNT - 1 ? CORAL : INK;
    ctx.globalAlpha = 1 - hide;
    ctx.beginPath();
    ctx.roundRect(px - w / 2, py, w, Math.max(w, bottom - py), w / 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  // The line draws through the tops, with a filled area and a glowing head.
  const f = tween(t, LINE_DRAW[0], LINE_DRAW[1]);
  const donut = tween(t, B(22.5), B(22.95), (x) => ease.outBack(x, 1.6));
  if (f > 0 && donut < 1) {
    const upto = Math.max(1, Math.floor(f * M));
    const area = (1 - tween(t, B(22), B(22.25))) * 0.16;
    if (area > 0) {
      ctx.beginPath();
      ctx.moveTo(pts[0][0], BASE);
      for (let j = 0; j <= upto; j++) ctx.lineTo(pts[j][0], pts[j][1]);
      ctx.lineTo(pts[upto][0], BASE);
      ctx.closePath();
      ctx.fillStyle = rgb(P.coral, area);
      ctx.fill();
    }
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let j = 1; j <= upto; j++) ctx.lineTo(pts[j][0], pts[j][1]);
    ctx.lineWidth = 7;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = INK;
    ctx.stroke();
    if (f < 1) disc(ctx, pts[upto][0], pts[upto][1], 13, CORAL);
  }

  // The closed ring thickens into a segmented donut.
  if (donut > 0) {
    const lw = lerp(7, 70, donut) * (1 + 0.08 * pulse(t - B(23), 8));
    const a0 = -Math.PI / 2 + spin;
    const gap = 0.035 * clamp(donut);
    const segs = [
      [0, 0.56, INK, 1],
      [0.56, 0.8, CORAL, tween(t, B(22.6), B(22.95), ease.outExpo)],
      [0.8, 1, BLUE, tween(t, B(22.75), B(23.1), ease.outExpo)],
    ];
    ctx.lineCap = "butt";
    ctx.lineWidth = lw;
    for (const [s0, s1, col, sweep] of segs) {
      if (sweep <= 0) continue;
      ctx.strokeStyle = col;
      ctx.beginPath();
      ctx.arc(
        RING[0],
        RING[1],
        RR,
        a0 + s0 * TAU + gap,
        a0 + lerp(s0, s1, sweep) * TAU - gap,
      );
      ctx.stroke();
    }
    const s = spring(t - B(22.7), 3, 0.45);
    if (s > 0) {
      ctx.save();
      ctx.translate(RING[0], RING[1]);
      ctx.scale(s, s);
      drawText(ctx, fonts.display, "15", {
        x: 0,
        y: 36,
        size: 150,
        wdth: 100,
        align: "center",
        color: INK,
      });
      mono(ctx, "SECONDS", 0, 80, rgb(P.ink, 0.6), {
        size: 14,
        tracking: 0.3,
        align: "center",
      });
      ctx.restore();
    }
  }
}

/* ------------------------------------------------------------------ */
/* 07 Rhythm: the reel folds into a grid of itself                     */
/* ------------------------------------------------------------------ */

const SCENES = [null, scene1, scene2, scene3, scene4, scene5, scene6];

function grid(n, gap) {
  const ch = (960 - (n - 1) * gap) / n;
  const cw = (ch * 16) / 9;
  const x0 = (W - (n * cw + (n - 1) * gap)) / 2;
  const y0 = (H - 960) / 2;
  const cell = (r, c) => [x0 + c * (cw + gap), y0 + r * (ch + gap), cw, ch];
  return { cell, cw, ch };
}
const G2 = grid(2, 20);
const G4 = grid(4, 14);
const G8 = grid(8, 8);

// [scene, start beat, playback rate]; the first four carry over from 2x2.
const CELLS = [
  { at: [0, 0], s: 1, b: 1.3, rate: 0.8 },
  { at: [0, 3], s: 3, b: 9.4, rate: 0.75 },
  { at: [3, 0], s: 5, b: 17.9, rate: 0.7 },
  { at: [3, 3], s: 6, b: 23.6, rate: 1 },
  { at: [0, 1], s: 2, b: 4.6, rate: 1 },
  { at: [0, 2], s: 4, b: 13, rate: 1 },
  { at: [1, 0], s: 6, b: 20.3, rate: 1 },
  { at: [1, 1], s: 2, b: 6.4, rate: 0.5 },
  { at: [1, 2], s: 5, b: 16.5, rate: 1 },
  { at: [1, 3], s: 1, b: 0.2, rate: 1 },
  { at: [2, 0], s: 3, b: 8.2, rate: 1 },
  { at: [2, 1], s: 5, b: 15.9, rate: 1 },
  { at: [2, 2], s: 6, b: 21.2, rate: 1 },
  { at: [2, 3], s: 2, b: 3, rate: 1 },
  { at: [3, 1], s: 3, b: 9.1, rate: 1 },
  { at: [3, 2], s: 4, b: 12.3, rate: 1 },
];
const DUMMY_FX = {};

function drawCell(ctx, rect, radius, cell, t, alpha = 1) {
  const [x, y, w, h] = rect;
  if (w < 1 || h < 1 || alpha <= 0) return;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, radius);
  ctx.clip();
  ctx.translate(x, y);
  ctx.scale(w / W, h / H);
  const lt = B(cell.b) + (t - B(23.6)) * cell.rate;
  SCENES[cell.s](ctx, lt, DUMMY_FX, {}, true);
  ctx.restore();
  ctx.strokeStyle = rgb(P.paper, 0.14 * alpha);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, radius);
  ctx.stroke();
}

const lerpRect = (a, b, t) => a.map((v, i) => lerp(v, b[i], t));
const scaleRect = ([x, y, w, h], s) => [
  x + (w * (1 - s)) / 2,
  y + (h * (1 - s)) / 2,
  w * s,
  h * s,
];

// Step-sequencer pattern shown by the 8x8 grid.
const PATTERN = [
  "10001000",
  "00100010",
  "11111111",
  "01010101",
  "00110011",
  "10100101",
  "11011011",
  "00000011",
];
const ROW_TONES = [
  P.coral,
  P.paper,
  P.blue,
  P.coral,
  P.paper,
  P.blue,
  P.coral,
  P.sun,
];

function scene7(ctx, t, fx, hud) {
  fillAll(ctx, rgb([24, 23, 21]));
  hud.color = P.paper;
  fx.bloom = 0.3;
  const b = t / BEAT;

  if (b < 26) {
    // 2x2, zooming out of the data scene, then subdividing to 4x4.
    const full = [0, 0, W, H];
    const toG4 = tween(t, B(24.8), B(25.05), ease.inOutExpo);
    const split = tween(t, B(25.85), B(26));
    CELLS.forEach((cell, i) => {
      const [r4, c4] = cell.at;
      const g4 = G4.cell(r4, c4);
      let rect;
      let radius = 12;
      if (i < 4) {
        const g2 = G2.cell(Math.floor(i / 2), i % 2);
        const q = tween(
          t,
          B(23.6) + (i === 3 ? 0 : 0.04 * i),
          B(24),
          ease.inOutExpo,
        );
        const offs = [
          [-900, -520],
          [900, -520],
          [-900, 520],
          [0, 0],
        ][i];
        const start =
          i === 3 ? full : [g2[0] + offs[0], g2[1] + offs[1], g2[2], g2[3]];
        rect = lerpRect(lerpRect(start, g2, q), g4, toG4);
        radius = lerp(i === 3 ? 0 : 14, 14, q);
      } else {
        const dist = Math.hypot(r4 - 1.5, c4 - 1.5);
        const s = spring(t - B(24.95) - 0.035 * dist, 3.5, 0.72);
        if (s <= 0) return;
        rect = scaleRect(g4, s);
      }
      drawCell(ctx, rect, radius, cell, t, 1 - split * 0.85);
    });
    // Tiles crack out of the 4x4 cells.
    if (split > 0) drawTiles(ctx, t, split);
  } else if (b < 27) {
    drawTiles(ctx, t, 1);
  } else {
    // Tiles round into dots and pour into the centre.
    for (let r = 0; r < 8; r++) {
      for (let c = 0; c < 8; c++) {
        const [x, y, w, h] = G8.cell(r, c);
        const dn = Math.hypot(r - 3.5, c - 3.5) / 5;
        const round = tween(t, B(27), B(27.12));
        const go = tween(t, B(27.02) + 0.1 * (1 - dn), B(27.45), ease.inCubic);
        const size = lerp(Math.min(w, h), 26, round) * (1 - 0.4 * go);
        const ang = Math.atan2(y + h / 2 - CY, x + w / 2 - CX) + go * 1.6;
        const d0 = Math.hypot(x + w / 2 - CX, y + h / 2 - CY);
        const d = d0 * (1 - go);
        const px = CX + Math.cos(ang) * d;
        const py = CY + Math.sin(ang) * d;
        const tone = mixRGB(
          PATTERN[r][c] === "1" ? ROW_TONES[r] : [40, 38, 35],
          P.coral,
          round,
        );
        ctx.fillStyle = rgb(tone);
        const ww = lerp(w, size, round);
        const hh = lerp(h, size, round);
        ctx.beginPath();
        ctx.roundRect(
          px - ww / 2,
          py - hh / 2,
          ww,
          hh,
          lerp(6, size / 2, round),
        );
        ctx.fill();
      }
    }
    // The last dot standing, inflating in the silence before the drop.
    const grow = spring(t - B(27.3), 3, 0.5);
    const hold = tween(t, B(27.5), B(28), ease.inCubic);
    const tremble = hold * hold * 3;
    disc(
      ctx,
      CX + Math.sin(t * 131) * tremble,
      CY + Math.cos(t * 97) * tremble,
      DOT_R * grow * (1 + 0.22 * hold),
      CORAL,
    );
  }
}

function drawTiles(ctx, t, q) {
  const e = ease.inOutCubic(q);
  const on = tween(t, B(26), B(26) + 0.02);
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      const target = G8.cell(r, c);
      // Parent 4x4 cell quadrant this tile cracks out of.
      const [px, py, pw, ph] = G4.cell(r >> 1, c >> 1);
      const start = [
        px + (c & 1) * (pw / 2),
        py + (r & 1) * (ph / 2),
        pw / 2,
        ph / 2,
      ];
      const rect = lerpRect(start, target, e);
      const lit = PATTERN[r][c] === "1";
      const stepT = B(26) + (c / 8) * BEAT;
      const flash = on * pulse(t - stepT, 9) * (t >= stepT ? 1 : 0);
      let tone = lit ? ROW_TONES[r] : [30, 29, 27];
      if (lit) tone = mixRGB(tone, P.paper, flash * 0.8);
      else tone = mixRGB(tone, [70, 66, 60], flash);
      ctx.globalAlpha = q;
      ctx.fillStyle = rgb(tone);
      ctx.beginPath();
      ctx.roundRect(...rect, 6);
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }
  // Playhead column.
  if (on > 0 && t < B(27)) {
    const c = Math.floor(((t - B(26)) / BEAT) * 8);
    const [x] = G8.cell(0, c);
    const [, y0] = G8.cell(0, 0);
    ctx.strokeStyle = rgb(P.paper, 0.9);
    ctx.lineWidth = 2;
    ctx.strokeRect(x - 5, y0 - 5, G8.cw + 10, 960 + 10);
  }
}

/* ------------------------------------------------------------------ */
/* 08 Hello                                                           */
/* ------------------------------------------------------------------ */

const endcard = (() => {
  const face = fonts.serif;
  const SIZE = 340;
  const L = layout(face, "Claude", { size: SIZE });
  const GAP = 10;
  const total = L.width + GAP + DOT_R * 2;
  const x0 = CX - total / 2;
  const BASE = 596;
  return {
    face,
    SIZE,
    x0,
    BASE,
    dot: [x0 + L.width + GAP + DOT_R, BASE - DOT_R],
  };
})();

function scene8(ctx, t, fx, hud) {
  fillAll(ctx, INK);
  fx.bloom = 0.28;
  fx.flash = 0.4 * pulse(t - B(28), 12);
  hud.color = P.paper;
  hud.alpha = 1 - tween(t, B(28), B(28.7));
  const { face, SIZE, x0, BASE, dot } = endcard;

  // Shockwave from the centre.
  for (const [delay, w] of [
    [0, 3],
    [0.09, 1.5],
  ]) {
    const p = norm(t, B(28) + delay, B(28) + delay + 0.9);
    if (p <= 0 || p >= 1) continue;
    ctx.strokeStyle = rgb(P.paper, 0.5 * (1 - p));
    ctx.lineWidth = w * (1 - p) + 0.5;
    ctx.beginPath();
    ctx.arc(CX, CY, 36 + 1100 * ease.outExpo(p), 0, TAU);
    ctx.stroke();
  }

  const push = 1 + 0.03 * norm(t, B(28.2), B(32));
  ctx.save();
  ctx.translate(CX, CY);
  ctx.scale(push, push);
  ctx.translate(-CX, -CY);

  // The name rises out of the baseline.
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, W, BASE + 10);
  ctx.clip();
  drawText(ctx, face, "Claude", {
    x: x0,
    y: BASE,
    size: SIZE,
    color: PAPER,
    letter: (i) => {
      const p = tween(
        t,
        B(28) + 0.04 + 0.05 * i,
        B(28) + 0.55 + 0.05 * i,
        ease.outExpo,
      );
      return { dy: (1 - p) * 300, rot: (1 - p) * 0.12 };
    },
  });
  ctx.restore();

  // The dot arcs over and lands as the full stop, then winks at the end.
  const p = norm(t, B(28), END_LAND);
  const [ex, ey] = dot;
  const x = lerp(CX, ex, p);
  let y = lerp(CY, ey, p) - 4 * 240 * p * (1 - p);
  const vy = ey - CY - 4 * 240 * (1 - 2 * p);
  const st = p < 1 ? 0.3 * Math.sin(Math.PI * p) : 0;
  const hop = norm(t, END_WINK, END_WINK + 0.28);
  if (hop > 0 && hop < 1) y -= 38 * Math.sin(Math.PI * hop);
  const d =
    jiggle(t, END_LAND, 0.5, 5.5, 11) +
    jiggle(t, END_WINK + 0.28, 0.35, 5.5, 11) +
    0.25 * tween(t, END_WINK - 0.12, END_WINK) * (t < END_WINK ? 1 : 0);
  if (p >= 1 && (hop <= 0 || hop >= 1)) y += DOT_R * d;
  blob(
    ctx,
    x,
    y,
    DOT_R,
    1 + 0.8 * d,
    1 - d,
    CORAL,
    st,
    Math.atan2(vy, ex - CX),
  );
  const ring = norm(t, END_WINK + 0.28, END_WINK + 0.9);
  if (ring > 0 && ring < 1) {
    ctx.strokeStyle = rgb(P.coral, 0.6 * (1 - ring));
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(ex, ey, DOT_R + 60 * ease.outCubic(ring), 0, TAU);
    ctx.stroke();
  }

  // Sub lines decode in.
  const step = Math.floor(t * 30);
  const sub = scramble(
    "MOTION DESIGN REEL · 2026",
    norm(t, B(28.7), B(29.6)),
    21,
    step,
  );
  mono(ctx, sub, CX, BASE + 112, rgb(P.paper, 0.78), {
    size: 21,
    tracking: 0.34,
    align: "center",
  });
  ctx.restore();

  const credit = scramble(
    "15 SECONDS · 900 FRAMES · ONE DOT",
    norm(t, B(29.4), B(30.3)),
    22,
    step,
  );
  mono(ctx, credit, CX, 1010, rgb(P.paper, 0.4), {
    size: 14,
    tracking: 0.3,
    align: "center",
  });
}

/* ------------------------------------------------------------------ */
/* HUD                                                                */
/* ------------------------------------------------------------------ */

function drawHUD(ctx, t, hud) {
  const a = hud.alpha ?? 1;
  if (a <= 0.001) return;
  const col = hud.color;
  const step = Math.floor(t * 30);
  const intro = (d) => norm(t, 0.05 + d, 0.5 + d);
  const text = (s, x, y, o = {}) =>
    mono(ctx, s, x, y, rgb(col, a * (o.alpha ?? 1)), { align: o.align });

  text(scramble("CLAUDE", intro(0), 1, step), 56, 70);
  text(scramble("MOTION DESIGN REEL", intro(0.06), 2, step), 56, 94, {
    alpha: 0.5,
  });

  const frame = Math.floor(t * FPS + 1e-4);
  const pad = (v) => String(v).padStart(2, "0");
  const tc = `00:00:${pad(Math.floor(frame / FPS))}:${pad(frame % FPS)}`;
  text(scramble(tc, intro(0.1), 3, step), W - 56, 70, { align: "right" });
  text(scramble("60 FPS  128 BPM", intro(0.16), 4, step), W - 56, 94, {
    align: "right",
    alpha: 0.5,
  });

  const b = t / BEAT;
  let ci = 0;
  for (let i = 0; i < CHAPTERS.length; i++) if (b >= CHAPTERS[i].beat) ci = i;
  const label = `${pad(ci + 1)} / ${CHAPTERS[ci].label}`;
  const cp = ci === 0 ? intro(0.2) : norm(t - B(CHAPTERS[ci].beat), 0, 0.3);
  text(scramble(label, cp, 10 + ci, step), 56, 1024);

  // Progress: one segment per chapter, plus a beat light.
  const grow = tween(t, 0.2, 0.7, ease.outExpo);
  const bw = 300;
  const bx = W - 56 - bw;
  const by = 1017;
  for (let i = 0; i < 8; i++) {
    const sx = bx + (i * bw) / 8;
    const w = (bw / 8 - 6) * grow;
    ctx.fillStyle = rgb(col, a * 0.22);
    ctx.fillRect(sx, by, w, 3);
    ctx.fillStyle = rgb(col, a);
    ctx.fillRect(sx, by, w * clamp((b - i * 4) / 4), 3);
  }
  const beat = pulse(t % BEAT, 9) * (t >= B(4) ? 1 : 0.4);
  disc(ctx, bx - 18, by + 1.5, (3.5 + 3 * beat) * grow, rgb(col, a));

  // Crop marks.
  const m = 16 * tween(t, 0, 0.45, ease.outExpo);
  ctx.strokeStyle = rgb(col, a * 0.5);
  ctx.lineWidth = 1.5;
  for (const [x, y, sx, sy] of [
    [28, 28, 1, 1],
    [W - 28, 28, -1, 1],
    [28, H - 28, 1, -1],
    [W - 28, H - 28, -1, -1],
  ]) {
    ctx.beginPath();
    ctx.moveTo(x + sx * m, y);
    ctx.lineTo(x, y);
    ctx.lineTo(x, y + sy * m);
    ctx.stroke();
  }
}

/* ------------------------------------------------------------------ */
/* Frame                                                              */
/* ------------------------------------------------------------------ */

const CA_HITS = [
  [4, 0.012],
  [8, 0.01],
  [12, 0.012],
  [16, 0.012],
  [20, 0.008],
  [24, 0.01],
  [25, 0.006],
  [26, 0.006],
  [28, 0.022],
];

export function drawFrame(ctx, t) {
  const fx = {
    bg: P.ink,
    balls: null,
    ca: 0,
    bloom: 0.2,
    flash: 0,
    grain: 0.028,
    vignette: 0.28,
  };
  const hud = { color: P.paper, alpha: 1 };
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 1;
  ctx.clearRect(0, 0, W, H);
  const b = t / BEAT;

  const shake =
    16 * pulse(t - B(4), 9) +
    22 * pulse(t - B(28), 8) +
    7 * pulse(t - B(16), 10) +
    6 * pulse(t - B(24), 10);
  ctx.save();
  if (shake > 0.2 && !(b >= 12 && b < 16)) {
    ctx.translate(Math.sin(t * 91.7) * shake, Math.cos(t * 77.3) * shake);
  }
  if (b < 4) scene1(ctx, t, fx, hud);
  else if (b < 8) scene2(ctx, t, fx, hud);
  else if (b < 12) scene3(ctx, t, fx, hud);
  else if (b < 16) scene4(ctx, t, fx, hud);
  else if (b < 19.85) scene5(ctx, t, fx, hud);
  else if (b < 20.25) {
    // The line of points opens into the next scene.
    scene5(ctx, t, fx, hud);
    const q = tween(t, B(19.85), B(20.25), ease.inOutExpo);
    const top = lerp(800, -2, q);
    const bottom = lerp(801, H + 2, q);
    ctx.save();
    ctx.beginPath();
    ctx.rect(-W, top, W * 3, bottom - top);
    ctx.clip();
    const inner = { ...fx };
    scene6(ctx, t, inner, q > 0.5 ? hud : {});
    ctx.restore();
  } else if (b < 23.6) scene6(ctx, t, fx, hud);
  else if (b < 28) scene7(ctx, t, fx, hud);
  else scene8(ctx, t, fx, hud);
  ctx.restore();

  drawHUD(ctx, t, hud);
  for (const [beat, amp] of CA_HITS) fx.ca += amp * pulse(t - B(beat), 9);
  if (t < B(8)) fx.ca += 0.012 * tween(t, B(7.6), B(8), ease.inExpo);
  return fx;
}
