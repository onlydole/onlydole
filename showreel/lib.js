// Math, easing and colour helpers. Everything is a pure function of its
// inputs so any frame can be rendered in any order.

export const TAU = Math.PI * 2;
export const GOLDEN = Math.PI * (3 - Math.sqrt(5));

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, t) => a + (b - a) * t;
export const norm = (x, a, b) => clamp((x - a) / (b - a));

export const ease = {
  linear: (t) => t,
  inQuad: (t) => t * t,
  outQuad: (t) => 1 - (1 - t) * (1 - t),
  inCubic: (t) => t * t * t,
  outCubic: (t) => 1 - (1 - t) ** 3,
  inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2),
  outQuart: (t) => 1 - (1 - t) ** 4,
  inOutQuart: (t) => (t < 0.5 ? 8 * t ** 4 : 1 - (-2 * t + 2) ** 4 / 2),
  inExpo: (t) => (t <= 0 ? 0 : 2 ** (10 * t - 10)),
  outExpo: (t) => (t >= 1 ? 1 : 1 - 2 ** (-10 * t)),
  inOutExpo: (t) => {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    return t < 0.5 ? 2 ** (20 * t - 10) / 2 : (2 - 2 ** (-20 * t + 10)) / 2;
  },
  outBack: (t, s = 1.70158) => 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2,
  inBack: (t, s = 1.70158) => (s + 1) * t * t * t - s * t * t,
};

/** Eased progress of `t` through the window [t0, t1]. */
export const tween = (t, t0, t1, fn = ease.inOutCubic) => fn(norm(t, t0, t1));

/**
 * Step response of a damped spring, `x` seconds after release.
 * Rises from 0 to 1 and overshoots when `damp` < 1.
 */
export function spring(x, freq = 3, damp = 0.45) {
  if (x <= 0) return 0;
  const w = TAU * freq;
  const wd = w * Math.sqrt(1 - damp * damp);
  const decay = Math.exp(-damp * w * x);
  return 1 - decay * (Math.cos(wd * x) + ((damp * w) / wd) * Math.sin(wd * x));
}

/** Exponentially decaying impulse, zero before it fires. */
export const pulse = (x, decay = 10) => (x < 0 ? 0 : Math.exp(-x * decay));

/** Deterministic hash of an integer to [0, 1). */
export function hash(n) {
  let x = Math.imul((n | 0) ^ 0x9e3779b9, 0x85ebca6b);
  x ^= x >>> 13;
  x = Math.imul(x, 0xc2b2ae35);
  x ^= x >>> 16;
  return (x >>> 0) / 4294967296;
}

/** Small seeded PRNG for building fixed layouts. */
export function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hex(c) {
  const n = Number.parseInt(c.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export const rgb = ([r, g, b], a = 1) =>
  a >= 1
    ? `rgb(${r | 0},${g | 0},${b | 0})`
    : `rgba(${r | 0},${g | 0},${b | 0},${a.toFixed(4)})`;

export const mixRGB = (a, b, t) => [
  lerp(a[0], b[0], t),
  lerp(a[1], b[1], t),
  lerp(a[2], b[2], t),
];

export const PALETTE = {
  ink: hex("#0e0d0c"),
  paper: hex("#f1ece2"),
  coral: hex("#f2663a"),
  blue: hex("#2f3bff"),
  sun: hex("#ffc83d"),
};
