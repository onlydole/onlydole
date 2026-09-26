// In-browser player for the reel, plus the hooks render.mjs uses to capture
// frames (?capture). Picture and sound share one clock: the audio context.

import {
  createReel,
  DURATION,
  FPS,
  renderSoundtrack,
  soundtrackWav,
} from "./reel.js";
import { B, CHAPTERS } from "./timeline.js";

const canvas = document.getElementById("reel");
const reel = createReel(canvas);
const params = new URLSearchParams(location.search);

function base64(bytes) {
  return new Promise((resolve) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1]);
    r.readAsDataURL(new Blob([bytes]));
  });
}

if (params.has("capture")) {
  const gl = canvas.getContext("webgl2");
  const pixels = new Uint8Array(canvas.width * canvas.height * 4);
  window.capture = {
    fps: FPS,
    frames: Math.round(DURATION * FPS),
    /** Render frame `i` and return raw RGBA rows, bottom row first. */
    async frame(i, samples = 1) {
      reel.render(i / FPS, { samples, seed: i });
      gl.readPixels(
        0,
        0,
        canvas.width,
        canvas.height,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        pixels,
      );
      return base64(pixels);
    },
    /** Render time `t` and return a PNG data URL. */
    still(t, samples = 1) {
      reel.render(t, { samples, seed: Math.round(t * FPS) });
      return canvas.toDataURL("image/png");
    },
    async wav() {
      return base64(await soundtrackWav());
    },
  };
  document.documentElement.dataset.ready = "true";
} else {
  const $ = (id) => document.getElementById(id);
  const ui = {
    play: $("play"),
    toggle: $("toggle"),
    scrub: $("scrub"),
    time: $("time"),
    mute: $("mute"),
    chapters: [...document.querySelectorAll("[data-chapter]")],
  };
  let audio = null;
  let buffer = null;
  let soundtrack = null;
  let source = null;
  let gain = null;
  let playing = false;
  let muted = false;
  let origin = 0;
  let offset = 0;
  let t = 0;

  const clock = () => (audio ? audio.currentTime : performance.now() / 1000);
  const last = DURATION - 1 / FPS;

  function show(time, samples = 1) {
    t = Math.min(last, Math.max(0, time));
    reel.render(t, { samples, seed: Math.round(t * FPS) });
    ui.scrub.value = String(Math.round(t * 1000));
    const frame = Math.floor(t * FPS + 1e-4);
    ui.time.textContent = `${String(Math.floor(frame / FPS)).padStart(2, "0")}:${String(frame % FPS).padStart(2, "0")}`;
    let active = 0;
    CHAPTERS.forEach((c, i) => {
      if (t >= B(c.beat)) active = i;
    });
    ui.chapters.forEach((el, i) => {
      if (i === active) el.setAttribute("aria-current", "step");
      else el.removeAttribute("aria-current");
    });
  }

  async function start() {
    if (playing) return;
    playing = true;
    document.body.classList.add("playing");
    ui.toggle.textContent = "Pause";
    if (!audio) {
      audio = new AudioContext();
      gain = audio.createGain();
      gain.connect(audio.destination);
      soundtrack = renderSoundtrack(audio.sampleRate);
    }
    // Every start waits on the same render; only one source ever plays.
    buffer = await soundtrack;
    await audio.resume();
    if (!playing || source) return;
    source = audio.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    source.connect(gain);
    gain.gain.value = muted ? 0 : 1;
    offset = t >= last ? 0 : t;
    origin = clock();
    source.start(0, offset);
    requestAnimationFrame(tick);
  }

  function stop() {
    playing = false;
    source?.stop();
    source = null;
    document.body.classList.remove("playing");
    ui.toggle.textContent = "Play";
    show(t, 6);
  }

  function tick() {
    if (!playing || !source) return;
    show((offset + clock() - origin) % DURATION);
    requestAnimationFrame(tick);
  }

  function seek(time) {
    const resume = playing;
    if (playing) stop();
    show(time, resume ? 1 : 6);
    if (resume) start();
  }

  ui.play.addEventListener("click", start);
  ui.toggle.addEventListener("click", () => (playing ? stop() : start()));
  ui.scrub.max = String(Math.round(DURATION * 1000));
  ui.scrub.addEventListener("input", () => {
    if (playing) stop();
    show(Number(ui.scrub.value) / 1000, 2);
  });
  ui.scrub.addEventListener("change", () => show(t, 6));
  ui.mute.addEventListener("click", () => {
    muted = !muted;
    if (gain) gain.gain.value = muted ? 0 : 1;
    ui.mute.textContent = muted ? "Sound off" : "Sound on";
    ui.mute.setAttribute("aria-pressed", String(muted));
  });
  ui.chapters.forEach((el) => {
    el.addEventListener("click", () =>
      seek(B(CHAPTERS[Number(el.dataset.chapter)].beat)),
    );
  });
  document.addEventListener("keydown", (e) => {
    if (e.target instanceof HTMLInputElement && e.key !== " ") return;
    if (e.key === " ") {
      e.preventDefault();
      if (playing) stop();
      else start();
    } else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      if (playing) stop();
      const step = (e.shiftKey ? 10 : 1) / FPS;
      show(t + (e.key === "ArrowRight" ? step : -step), 6);
    }
  });

  show(14.2, 6);
}
