// The soundtrack, synthesised with the Web Audio API and rendered offline,
// so every hit lands on the same beat grid the picture uses.
// A minor for the build, a Picardy A major 9 for the name.

import { rng } from "./lib.js";
import {
  B,
  BAR_DELAY,
  BARS,
  BEAT,
  BOUNCES,
  DOT_HOP,
  DOT_LAND,
  DURATION,
  END_LAND,
  END_WINK,
  LINE_DRAW,
} from "./timeline.js";

const mtof = (m) => 440 * 2 ** ((m - 69) / 12);
const PENTA = [69, 72, 74, 76, 79, 81, 84, 86, 88, 91];

class Studio {
  constructor(ctx) {
    this.ctx = ctx;
    this.rand = rng(2026);
    this.kicks = [];

    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -18;
    comp.knee.value = 10;
    comp.ratio.value = 3.5;
    comp.attack.value = 0.005;
    comp.release.value = 0.2;
    comp.connect(ctx.destination);
    this.master = this.gain(0.8, comp);

    this.drums = this.gain(0.9, this.master);
    this.duck = this.gain(1, this.master);
    this.music = this.gain(0.6, this.duck);
    this.fx = this.gain(0.7, this.master);

    this.verb = ctx.createConvolver();
    this.verb.buffer = this.impulse(2.6);
    this.verb.connect(this.gain(0.3, this.master));

    this.echo = ctx.createDelay(1);
    this.echo.delayTime.value = BEAT * 0.75;
    const tone = ctx.createBiquadFilter();
    tone.frequency.value = 2800;
    const fb = this.gain(0.34, this.echo);
    this.echo.connect(tone);
    tone.connect(fb);
    tone.connect(this.gain(0.24, this.master));

    const len = ctx.sampleRate * 2;
    this.noise = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = this.noise.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = this.rand() * 2 - 1;
  }

  gain(v, to) {
    const g = this.ctx.createGain();
    g.gain.value = v;
    if (to) g.connect(to);
    return g;
  }

  impulse(seconds) {
    const { sampleRate } = this.ctx;
    const len = Math.floor(seconds * sampleRate);
    const buf = this.ctx.createBuffer(2, len, sampleRate);
    for (let ch = 0; ch < 2; ch++) {
      const d = buf.getChannelData(ch);
      let lp = 0;
      for (let i = 0; i < len; i++) {
        const x = this.rand() * 2 - 1;
        const k = i / len;
        lp += (x - lp) * (0.6 - 0.45 * k);
        d[i] = lp * (1 - k) ** 3.2;
      }
    }
    return buf;
  }

  /** Attack to `peak`, exponential decay to silence. */
  env(param, t, attack, peak, decay) {
    param.setValueAtTime(0, t);
    param.linearRampToValueAtTime(peak, t + attack);
    param.exponentialRampToValueAtTime(0.0001, t + attack + decay);
  }

  route(node, bus, { pan = 0, verb = 0, echo = 0 } = {}) {
    let out = node;
    if (pan) {
      const p = this.ctx.createStereoPanner();
      p.pan.value = pan;
      node.connect(p);
      out = p;
    }
    out.connect(bus);
    if (verb) out.connect(this.gain(verb, this.verb));
    if (echo) out.connect(this.gain(echo, this.echo));
    return out;
  }

  osc(type, f, t, dur) {
    const o = this.ctx.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(f, t);
    o.start(t);
    o.stop(t + dur);
    return o;
  }

  noiseAt(t, dur) {
    const s = this.ctx.createBufferSource();
    s.buffer = this.noise;
    s.loop = true;
    s.start(t, this.rand() * 1.5);
    s.stop(t + dur);
    return s;
  }

  filter(type, f, q = 0.7) {
    const b = this.ctx.createBiquadFilter();
    b.type = type;
    b.frequency.value = f;
    b.Q.value = q;
    return b;
  }

  chain(...nodes) {
    for (let i = 0; i < nodes.length - 1; i++) nodes[i].connect(nodes[i + 1]);
    return nodes[nodes.length - 1];
  }

  // ---- Drums --------------------------------------------------------

  kick(t, v = 0.9) {
    const o = this.osc("sine", 180, t, 0.5);
    o.frequency.exponentialRampToValueAtTime(60, t + 0.05);
    o.frequency.exponentialRampToValueAtTime(42, t + 0.35);
    const g = this.gain(0);
    this.env(g.gain, t, 0.002, v, 0.42);
    this.route(this.chain(o, g), this.drums);
    const click = this.gain(0);
    this.env(click.gain, t, 0.001, 0.22 * v, 0.012);
    this.route(
      this.chain(this.noiseAt(t, 0.03), this.filter("highpass", 3000), click),
      this.drums,
    );
    this.kicks.push(t);
  }

  clap(t, v = 0.42) {
    for (const [dt, dec] of [
      [0, 0.012],
      [0.012, 0.012],
      [0.024, 0.2],
    ]) {
      const g = this.gain(0);
      this.env(g.gain, t + dt, 0.001, v, dec);
      const out = this.chain(
        this.noiseAt(t + dt, dec + 0.1),
        this.filter("bandpass", 1400, 0.9),
        g,
      );
      this.route(out, this.drums, { verb: 0.25 });
    }
  }

  hat(t, v = 0.14, open = false, pan = 0) {
    const g = this.gain(0);
    this.env(g.gain, t, 0.001, v, open ? 0.26 : 0.04);
    const out = this.chain(
      this.noiseAt(t, open ? 0.4 : 0.1),
      this.filter("highpass", 7500),
      this.filter("peaking", 10500, 0.8),
      g,
    );
    this.route(out, this.drums, { pan });
  }

  snare(t, v = 0.3, tune = 1) {
    const g = this.gain(0);
    this.env(g.gain, t, 0.001, v, 0.14);
    this.route(
      this.chain(
        this.noiseAt(t, 0.25),
        this.filter("bandpass", 1900 * tune, 0.7),
        g,
      ),
      this.drums,
      {
        verb: 0.15,
      },
    );
    const o = this.osc("triangle", 190 * tune, t, 0.2);
    o.frequency.exponentialRampToValueAtTime(150 * tune, t + 0.1);
    const g2 = this.gain(0);
    this.env(g2.gain, t, 0.001, v * 0.5, 0.08);
    this.route(this.chain(o, g2), this.drums);
  }

  crash(t, v = 0.3) {
    const g = this.gain(0);
    this.env(g.gain, t, 0.002, v, 1.8);
    this.route(
      this.chain(this.noiseAt(t, 2.2), this.filter("highpass", 5200), g),
      this.drums,
      {
        verb: 0.35,
      },
    );
  }

  boom(t, v = 0.7) {
    const o = this.osc("sine", 64, t, 1.8);
    o.frequency.exponentialRampToValueAtTime(34, t + 1.2);
    const g = this.gain(0);
    this.env(g.gain, t, 0.004, v, 1.5);
    const shaper = this.ctx.createWaveShaper();
    const curve = new Float32Array(1024);
    for (let i = 0; i < curve.length; i++) {
      curve[i] = Math.tanh(((i / (curve.length - 1)) * 2 - 1) * 2.2);
    }
    shaper.curve = curve;
    this.route(this.chain(o, g, shaper), this.master);
  }

  // ---- Tonal ----------------------------------------------------------

  bloop(t, f, v = 0.35, pan = 0) {
    const o = this.osc("sine", f * 2.4, t, 0.4);
    o.frequency.exponentialRampToValueAtTime(f, t + 0.045);
    const g = this.gain(0);
    this.env(g.gain, t, 0.002, v, 0.28);
    this.route(this.chain(o, g), this.fx, { pan, verb: 0.22, echo: 0.28 });
    const h = this.osc("sine", f * 2, t, 0.15);
    const g2 = this.gain(0);
    this.env(g2.gain, t, 0.001, v * 0.15, 0.1);
    this.route(this.chain(h, g2), this.fx, { pan });
  }

  tick(t, f, v = 0.05, pan = 0) {
    const g = this.gain(0);
    this.env(g.gain, t, 0.001, v, 0.035);
    this.route(this.chain(this.osc("sine", f, t, 0.06), g), this.fx, {
      pan,
      verb: 0.1,
    });
  }

  tock(t, f, v = 0.16) {
    const o = this.osc("triangle", f * 1.6, t, 0.12);
    o.frequency.exponentialRampToValueAtTime(f, t + 0.02);
    const g = this.gain(0);
    this.env(g.gain, t, 0.001, v, 0.07);
    this.route(this.chain(o, g), this.fx, { verb: 0.12 });
  }

  pluck(t, f, v = 0.085, pan = 0, len = 0.22) {
    const lp = this.filter("lowpass", 5200, 3);
    lp.frequency.setValueAtTime(5200, t);
    lp.frequency.exponentialRampToValueAtTime(600, t + len);
    const g = this.gain(0);
    this.env(g.gain, t, 0.003, v, len);
    this.osc("sawtooth", f, t, len + 0.1).connect(lp);
    this.osc("sawtooth", f * 1.004, t, len + 0.1).connect(lp);
    this.route(this.chain(lp, g), this.music, { pan, verb: 0.15, echo: 0.18 });
  }

  pad(t0, t1, notes, v = 0.03, o = {}) {
    const {
      from = 1800,
      to = from,
      release = 0.35,
      attack = 0.12,
      fade = 1,
    } = o;
    for (const m of notes) {
      const f = mtof(m);
      const lp = this.filter("lowpass", from, 0.8);
      lp.frequency.setValueAtTime(from, t0);
      lp.frequency.exponentialRampToValueAtTime(to, t1);
      const g = this.gain(0);
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(v, t0 + attack);
      g.gain.linearRampToValueAtTime(v * fade, t1);
      g.gain.linearRampToValueAtTime(0, t1 + release);
      for (const [cents, pan] of [
        [-10, -0.6],
        [0, 0],
        [10, 0.6],
      ]) {
        const osc = this.osc("sawtooth", f, t0, t1 - t0 + release + 0.05);
        osc.detune.value = cents;
        const p = this.ctx.createStereoPanner();
        p.pan.value = pan;
        this.chain(osc, p, lp);
      }
      this.route(this.chain(lp, g), this.music, { verb: 0.3 });
    }
  }

  bass(t, f, dur, v = 0.3) {
    const lp = this.filter("lowpass", 1100, 4);
    lp.frequency.setValueAtTime(1100, t);
    lp.frequency.exponentialRampToValueAtTime(280, t + 0.15);
    const g = this.gain(0);
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(v, t + 0.004);
    g.gain.setValueAtTime(v * 0.8, t + dur);
    g.gain.linearRampToValueAtTime(0, t + dur + 0.05);
    this.osc("sawtooth", f, t, dur + 0.1).connect(lp);
    const sub = this.osc("sine", f, t, dur + 0.1);
    const sg = this.gain(0.8);
    this.chain(sub, sg, g);
    this.chain(lp, g);
    this.route(g, this.music);
  }

  bell(t, f, v = 0.09, pan = 0) {
    const car = this.osc("sine", f, t, 2.6);
    const mod = this.osc("sine", f * 3.01, t, 2.6);
    const idx = this.gain(0);
    idx.gain.setValueAtTime(f * 2.2, t);
    idx.gain.exponentialRampToValueAtTime(f * 0.15, t + 1.2);
    this.chain(mod, idx, car.frequency);
    const g = this.gain(0);
    this.env(g.gain, t, 0.002, v, 2.3);
    this.route(this.chain(car, g), this.fx, { pan, verb: 0.4, echo: 0.2 });
  }

  glide(times, freqs, v = 0.05) {
    const t0 = times[0];
    const t1 = times[times.length - 1];
    const o = this.osc("sine", freqs[0], t0, t1 - t0 + 0.2);
    times.forEach((tt, i) => {
      o.frequency.linearRampToValueAtTime(freqs[i], tt);
    });
    const g = this.gain(0);
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(v, t0 + 0.03);
    g.gain.setValueAtTime(v, t1);
    g.gain.linearRampToValueAtTime(0, t1 + 0.1);
    this.route(this.chain(o, g), this.fx, { verb: 0.2, echo: 0.3 });
  }

  // ---- Noise FX ---------------------------------------------------------

  whoosh(t, dur, v = 0.18, up = true, pan = [-0.7, 0.7]) {
    const bp = this.filter("bandpass", 1000, 1.4);
    bp.frequency.setValueAtTime(up ? 350 : 5000, t);
    bp.frequency.exponentialRampToValueAtTime(up ? 5000 : 350, t + dur);
    const g = this.gain(0);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(v, t + dur * 0.75);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    const p = this.ctx.createStereoPanner();
    p.pan.setValueAtTime(pan[0], t);
    p.pan.linearRampToValueAtTime(pan[1], t + dur);
    this.chain(this.noiseAt(t, dur + 0.05), bp, g, p);
    this.route(p, this.fx, { verb: 0.25 });
  }

  riser(t0, t1, v = 0.2) {
    const hp = this.filter("highpass", 300);
    hp.frequency.setValueAtTime(300, t0);
    hp.frequency.exponentialRampToValueAtTime(7000, t1);
    const g = this.gain(0);
    g.gain.setValueAtTime(0.0005, t0);
    g.gain.exponentialRampToValueAtTime(v, t1);
    g.gain.setValueAtTime(0, t1 + 0.002);
    this.route(this.chain(this.noiseAt(t0, t1 - t0 + 0.01), hp, g), this.fx);
    const o = this.osc("sawtooth", 90, t0, t1 - t0 + 0.01);
    o.frequency.exponentialRampToValueAtTime(720, t1);
    const g2 = this.gain(0);
    g2.gain.setValueAtTime(0.0005, t0);
    g2.gain.exponentialRampToValueAtTime(v * 0.35, t1);
    g2.gain.setValueAtTime(0, t1 + 0.002);
    this.route(this.chain(o, this.filter("lowpass", 2500), g2), this.fx);
  }

  swell(t0, t1, v = 0.15) {
    const g = this.gain(0);
    g.gain.setValueAtTime(0.0005, t0);
    g.gain.exponentialRampToValueAtTime(v, t1);
    g.gain.setValueAtTime(0, t1 + 0.004);
    this.route(
      this.chain(
        this.noiseAt(t0, t1 - t0 + 0.01),
        this.filter("highpass", 2500),
        g,
      ),
      this.fx,
      {
        verb: 0.2,
      },
    );
  }

  shimmer(t, v = 0.08) {
    const bp = this.filter("bandpass", 9000, 2);
    bp.frequency.setValueAtTime(9000, t);
    bp.frequency.exponentialRampToValueAtTime(2500, t + 0.5);
    const g = this.gain(0);
    this.env(g.gain, t, 0.01, v, 0.5);
    this.route(this.chain(this.noiseAt(t, 0.6), bp, g), this.fx, { verb: 0.3 });
  }

  // Sidechain: the music bus ducks under every kick.
  applyDuck() {
    const g = this.duck.gain;
    for (const k of [...this.kicks].sort((a, b) => a - b)) {
      g.setValueAtTime(1, k);
      g.linearRampToValueAtTime(0.32, k + 0.008);
      g.linearRampToValueAtTime(1, k + 0.3);
    }
  }
}

const CHORDS = [
  [4, [53, 57, 60, 64]], // Fmaj7
  [8, [55, 59, 62, 64]], // G6
  [12, [57, 60, 64, 67, 71]], // Am9
  [16, [53, 57, 60, 64, 67]], // Fmaj9
  [20, [55, 59, 62, 69]], // Gadd9
  [24, [52, 57, 59, 62]], // E7sus4
  [26, [52, 56, 59, 62]], // E7
];
const chordAt = (beat) => {
  let c = CHORDS[0][1];
  for (const [b, notes] of CHORDS) if (beat >= b) c = notes;
  return c;
};

function score(s) {
  // Bar 0: the ball. Open fifths, HUD ticks, a bloop per bounce.
  s.pad(0.15, B(4), [57, 64, 71, 76], 0.02, {
    from: 380,
    to: 1600,
    release: 0.1,
  });
  for (let i = 0; i < 6; i++)
    s.tick(0.06 + i * 0.055, 2600 + 400 * (i % 3), 0.04, i % 2 ? 0.4 : -0.4);
  const notes = [69, 72, 76, 79, 81];
  const vels = [0.5, 0.42, 0.34, 0.28, 0.3];
  BOUNCES.forEach((t, i) => {
    s.bloop(t, mtof(notes[i]), vels[i], -0.3 + i * 0.15);
  });
  s.riser(B(3), B(4), 0.22);
  s.whoosh(B(3.5), 0.4, 0.2, true);

  // B4: the drop.
  s.boom(B(4), 0.7);
  s.crash(B(4), 0.35);
  for (let b = 4; b < 27.5; b++) s.kick(B(b), b === 4 ? 1 : 0.9);
  for (let b = 5; b < 27.5; b += 2) s.clap(B(b), 0.42);
  for (let b = 4; b < 27; b++) {
    s.hat(B(b + 0.5), b % 4 === 3 ? 0.12 : 0.14, b % 4 === 3, 0.2);
    if (b >= 16 && b < 26) {
      s.hat(B(b + 0.25), 0.06, false, -0.3);
      s.hat(B(b + 0.75), 0.07, false, 0.3);
    }
  }
  CHORDS.forEach(([b, n], i) => {
    const end = i + 1 < CHORDS.length ? CHORDS[i + 1][0] : 27.5;
    s.pad(B(b), B(end), n, 0.028, { release: end === 27.5 ? 0.06 : 0.3 });
  });
  for (let b = 4; b < 27; b++) {
    const root = Math.min(...chordAt(b)) - 12;
    s.bass(B(b + 0.5), mtof(root + (b % 4 === 3 ? 12 : 0)), B(0.42), 0.3);
  }
  const pat = [0, 2, 1, 3, 2, 4, 3, 1];
  for (let st = 32; st < 110; st++) {
    const b = st / 4;
    const tones = chordAt(b).map((n) => n + 12);
    const n = tones[pat[st % 8] % tones.length];
    s.pluck(B(b), mtof(n), st % 4 === 0 ? 0.085 : 0.06, st % 2 ? 0.35 : -0.35);
  }

  // 02 Kinetic type.
  for (let j = 0; j < 3; j++) s.tock(B(5) + 0.045 * j, 900 + 120 * j);
  s.bloop(DOT_LAND, mtof(81), 0.38);
  s.whoosh(B(6) - 0.08, 0.35, 0.16, true);
  for (let i = 0; i < 7; i++) s.tick(B(7) + 0.03 * i, 1800 + 150 * i, 0.06);
  s.tick(DOT_HOP[0], 1200, 0.08);
  s.bloop(DOT_HOP[1], mtof(84), 0.34);
  s.riser(B(7.6), B(8), 0.2);
  s.whoosh(B(7.55), 0.45, 0.2, true);

  // 03 Pattern.
  s.bloop(B(8), mtof(76), 0.3);
  for (let k = 0; k < 24; k++) {
    const t = B(8) + 0.06 + 0.32 * (k / 23) ** 1.2;
    s.tick(t, mtof(PENTA[k % 10] + 12), 0.035, Math.sin(k * 2.4) * 0.7);
  }
  s.shimmer(B(9));
  s.whoosh(B(9.5), 0.6, 0.12, false);
  s.swell(B(11.5), B(12), 0.18);

  // 04 Liquid.
  s.bloop(B(12), mtof(57), 0.4);
  s.bloop(B(12) + 0.03, mtof(64), 0.3);
  s.bloop(B(12) + 0.06, mtof(69), 0.25);
  [45, 48, 52].forEach((m, i) => {
    s.bloop(B(13 + i) + 0.02, mtof(m + 12), 0.22);
  });
  s.riser(B(15), B(16), 0.2);
  s.whoosh(B(15.3), 0.7, 0.18, true);

  // 05 Dimension.
  s.crash(B(16), 0.3);
  s.boom(B(16), 0.35);
  s.glide([B(16.35), B(17.25)], [400, 1600], 0.04);
  s.whoosh(B(16.9) - 0.05, 0.45, 0.14, true, [-0.6, 0.6]);
  s.whoosh(B(17.9) - 0.05, 0.45, 0.14, true, [0.6, -0.6]);
  s.whoosh(B(18.85), 0.55, 0.16, false, [-0.7, 0.7]);

  // 06 Data: bars and the line are sonified from the data itself.
  BARS.forEach((h, k) => {
    const note = PENTA[Math.round(h * (PENTA.length - 1))];
    s.tick(BAR_DELAY(k) + 0.12, mtof(note), 0.09, -0.5 + k / 15);
  });
  const [l0, l1] = LINE_DRAW;
  s.glide(
    BARS.map((_, k) => l0 + ((l1 - l0) * k) / (BARS.length - 1)),
    BARS.map((h) => mtof(69 + h * 24)),
    0.05,
  );
  const dur = B(21.6) - B(20.1);
  for (let k = 1; k <= 14; k++) {
    const u = -Math.log2(1 - (60 * k) / 900.01) / 10;
    s.tick(B(20.1) + u * dur, 3200, 0.03, 0.5);
  }
  s.whoosh(B(22), 0.6, 0.16, true, [0.8, -0.8]);
  [81, 84, 88].forEach((m, i) => {
    s.pluck(B(22.55) + 0.15 * i, mtof(m), 0.12, 0, 0.3);
  });

  // 07 Rhythm.
  s.whoosh(B(23.55), 0.45, 0.18, false);
  s.crash(B(24), 0.32);
  for (let i = 0; i < 12; i++)
    s.tick(B(24.95) + 0.03 * i, 1400 + 90 * i, 0.045);
  [0, 3, 5, 7, 10, 12, 15, 17].forEach((st, c) => {
    s.tick(B(26 + c / 8), mtof(76 + st), 0.07);
  });
  for (let i = 0; i < 4; i++)
    s.snare(B(26 + i / 4), 0.14 + 0.1 * (i / 4), 1 + 0.1 * i);
  for (let i = 0; i < 4; i++)
    s.snare(B(27 + i / 8), 0.25 + 0.3 * (i / 4), 1.3 + 0.12 * i);
  s.riser(B(26), B(27.5), 0.3);
  s.swell(B(27), B(27.5), 0.15);
  s.swell(B(27.55), B(28), 0.1);

  // 08 Hello: A major 9, bells, and the dot's last two bloops.
  s.kick(B(28), 1);
  s.boom(B(28), 0.6);
  s.crash(B(28), 0.45);
  s.pad(B(28), DURATION + 0.5, [45, 52, 56, 59, 61, 64, 68], 0.026, {
    from: 1200,
    to: 3200,
    attack: 0.02,
    fade: 0.45,
  });
  s.bass(B(28), mtof(33), 1.1, 0.26);
  [81, 85, 88, 92, 95].forEach((m, i) => {
    s.bell(B(28) + 0.02 + 0.08 * i, mtof(m), 0.08, -0.4 + 0.2 * i);
  });
  s.bloop(END_LAND, mtof(81), 0.35);
  for (let i = 0; i < 12; i++)
    s.tick(B(28.7) + i * 0.04, 2200 + 300 * (i % 4), 0.03);
  for (let i = 0; i < 9; i++)
    s.tick(B(29.4) + i * 0.05, 2600 + 200 * (i % 3), 0.02);
  s.bloop(END_WINK + 0.28, mtof(88), 0.25);
}

/** Render the full soundtrack to an AudioBuffer. */
export async function renderSoundtrack(sampleRate = 48000) {
  const length = Math.round(DURATION * sampleRate);
  const ctx = new OfflineAudioContext(2, length, sampleRate);
  const studio = new Studio(ctx);
  score(studio);
  studio.applyDuck();
  const buf = await ctx.startRendering();

  // Normalise to -1 dBFS, with a short fade at each end.
  let peak = 0;
  for (let ch = 0; ch < buf.numberOfChannels; ch++) {
    for (const v of buf.getChannelData(ch)) peak = Math.max(peak, Math.abs(v));
  }
  const gain = peak > 0 ? 0.891 / peak : 1;
  const fadeIn = Math.round(0.005 * sampleRate);
  const fadeOut = Math.round(0.3 * sampleRate);
  for (let ch = 0; ch < buf.numberOfChannels; ch++) {
    const d = buf.getChannelData(ch);
    for (let i = 0; i < length; i++) {
      let g = gain;
      if (i < fadeIn) g *= i / fadeIn;
      if (i > length - fadeOut) g *= (length - i) / fadeOut;
      d[i] *= g;
    }
  }
  return buf;
}

/** 16-bit PCM WAV bytes for an AudioBuffer. */
export function toWav(buf) {
  const ch = buf.numberOfChannels;
  const n = buf.length;
  const bytes = new ArrayBuffer(44 + n * ch * 2);
  const v = new DataView(bytes);
  const str = (o, s) => {
    for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i));
  };
  str(0, "RIFF");
  v.setUint32(4, 36 + n * ch * 2, true);
  str(8, "WAVE");
  str(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, ch, true);
  v.setUint32(24, buf.sampleRate, true);
  v.setUint32(28, buf.sampleRate * ch * 2, true);
  v.setUint16(32, ch * 2, true);
  v.setUint16(34, 16, true);
  str(36, "data");
  v.setUint32(40, n * ch * 2, true);
  const chans = Array.from({ length: ch }, (_, i) => buf.getChannelData(i));
  let o = 44;
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < ch; c++) {
      const s = Math.max(-1, Math.min(1, chans[c][i]));
      v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      o += 2;
    }
  }
  return new Uint8Array(bytes);
}
