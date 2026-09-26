// Shared clock for picture and sound. Every visual cue and every audio event
// is expressed in beats, so the two can never drift apart.

export const W = 1920;
export const H = 1080;
export const FPS = 60;
export const BPM = 128;
export const BEAT = 60 / BPM;
export const BEATS = 32;
export const DURATION = BEATS * BEAT; // 15.000 s, 8 bars of 4/4

/** Beat number to seconds. */
export const B = (n) => n * BEAT;

// Scene 1: the ball lands on these beats, each bounce half as tall as the last.
export const BOUNCES = [B(1), B(2), B(2.5), B(2.75), B(3)];

// Scene 2: the dot drops onto line one, then hops down to line three.
export const DOT_LAND = B(5.5);
export const DOT_HOP = [B(7.3), B(7.55)];

// Scene 6: sixteen bars rise one after another.
export const BAR_COUNT = 16;
export const BAR_DELAY = (k) => B(20) + 0.05 + 0.03 * k;
export const BARS = [
  0.18, 0.3, 0.24, 0.42, 0.36, 0.52, 0.47, 0.63, 0.55, 0.72, 0.66, 0.81, 0.74,
  0.9, 0.84, 1,
];
export const LINE_DRAW = [B(21.15), B(21.7)];

// Scene 8: the dot arcs from centre to become the full stop in "Claude."
export const END_LAND = B(28.5);
export const END_WINK = B(31);

export const CHAPTERS = [
  { beat: 0, label: "SQUASH & STRETCH" },
  { beat: 4, label: "KINETIC TYPE" },
  { beat: 8, label: "PATTERN & STAGGER" },
  { beat: 12, label: "LIQUID" },
  { beat: 16, label: "DIMENSION" },
  { beat: 20, label: "DATA" },
  { beat: 24, label: "RHYTHM" },
  { beat: 28, label: "HELLO" },
];
