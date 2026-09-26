// Wires the 2D scene layer into the WebGL compositor. Used by the in-browser
// player and by render.mjs, which drives it frame by frame.

import { renderSoundtrack, toWav } from "./audio.js";
import { Compositor } from "./gl.js";
import { drawFrame } from "./scenes.js";
import { DURATION, FPS, H, W } from "./timeline.js";

export { DURATION, FPS, H, W };

export function createReel(canvas) {
  const layer = document.createElement("canvas");
  layer.width = W;
  layer.height = H;
  const ctx = layer.getContext("2d", { willReadFrequently: true });
  const comp = new Compositor(canvas, W, H);
  const last = DURATION - 1e-6;

  /**
   * Render time `t`. With `samples` > 1 the frame integrates the scene
   * across a shutter of `shutter` frames, which is real motion blur.
   */
  function render(t, { samples = 1, shutter = 0.5, seed = 0 } = {}) {
    comp.begin();
    let fx;
    for (let s = 0; s < samples; s++) {
      const ts = samples > 1 ? t + (((s + 0.5) / samples) * shutter) / FPS : t;
      fx = drawFrame(ctx, Math.min(Math.max(ts, 0), last));
      comp.add(layer, fx, 1 / samples);
    }
    comp.end(fx, seed);
  }

  return { render, layer };
}

export async function soundtrackWav() {
  return toWav(await renderSoundtrack());
}

export { renderSoundtrack };
