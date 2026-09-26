// Renders the reel to MP4. Headless Chromium draws each frame (several
// sub-frames each, for motion blur), raw pixels stream straight into ffmpeg,
// and the Web Audio soundtrack is rendered offline and muxed alongside.
//
//   node render.mjs                     full render to showreel.mp4
//   node render.mjs --stills 1.2,7.9    PNG stills of chosen times
//   node render.mjs --audio             soundtrack only, to .frames/
//   node render.mjs --serve             serve the live player on :8080
//
// Options: --samples 8 --workers 3 --crf 19 --out showreel.mp4
// Set FFMPEG to an ffmpeg build with libx264 if it is not on PATH, and
// CHROMIUM to a Chromium binary to use instead of Playwright's download.

import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { cpus } from "node:os";
import { extname, join, normalize, sep } from "node:path";
import { parseArgs } from "node:util";
import { chromium } from "playwright";

const ROOT = import.meta.dirname;
const W = 1920;
const H = 1080;
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mp4": "video/mp4",
  ".jpg": "image/jpeg",
  ".png": "image/png",
};

const { values: opt } = parseArgs({
  options: {
    serve: { type: "boolean", default: false },
    audio: { type: "boolean", default: false },
    stills: { type: "string" },
    samples: { type: "string", default: "8" },
    workers: {
      type: "string",
      default: String(Math.max(1, Math.min(4, cpus().length - 1))),
    },
    crf: { type: "string", default: "19" },
    out: { type: "string", default: "showreel.mp4" },
    port: { type: "string", default: "8080" },
  },
});
const FFMPEG = process.env.FFMPEG ?? "ffmpeg";

function serve(port) {
  const server = createServer(async (req, res) => {
    let path;
    try {
      path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    } catch {
      res.writeHead(400).end();
      return;
    }
    const file = normalize(join(ROOT, path === "/" ? "index.html" : path));
    if (!file.startsWith(ROOT + sep)) {
      res.writeHead(403).end();
      return;
    }
    try {
      const body = await readFile(file);
      res.writeHead(200, {
        "content-type": TYPES[extname(file)] ?? "application/octet-stream",
      });
      res.end(body);
    } catch {
      res.writeHead(404).end();
    }
  });
  return new Promise((resolve) => {
    server.listen(port, "127.0.0.1", () => {
      resolve({ url: `http://127.0.0.1:${server.address().port}`, server });
    });
  });
}

async function openPage(url) {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM,
    args: [
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
      "--ignore-gpu-blocklist",
    ],
  });
  const page = await browser.newPage({
    viewport: { width: 1280, height: 800 },
  });
  page.on("pageerror", (e) => console.error("page error:", e.message));
  await page.goto(`${url}/index.html?capture`);
  await page.waitForFunction(
    () => document.documentElement.dataset.ready === "true",
  );
  return { browser, page };
}

function ffmpeg(args) {
  const p = spawn(
    FFMPEG,
    ["-hide_banner", "-loglevel", "error", "-y", ...args],
    {
      stdio: ["pipe", "inherit", "inherit"],
    },
  );
  const done = once(p, "close").then(([code]) => {
    if (code !== 0) throw new Error(`ffmpeg exited with ${code}`);
  });
  return { p, done };
}

async function stills(url, times, samples) {
  const dir = join(ROOT, ".frames");
  await mkdir(dir, { recursive: true });
  const { browser, page } = await openPage(url);
  for (const t of times) {
    const data = await page.evaluate(
      ([t, s]) => window.capture.still(t, s),
      [t, samples],
    );
    const file = join(dir, `still-${t.toFixed(3)}.png`);
    await writeFile(file, Buffer.from(data.split(",")[1], "base64"));
    console.log(file);
  }
  await browser.close();
}

async function soundtrack(page, dir) {
  const wav = join(dir, "soundtrack.wav");
  await writeFile(
    wav,
    Buffer.from(await page.evaluate(() => window.capture.wav()), "base64"),
  );
  return wav;
}

async function video(url, samples, workers) {
  const dir = join(ROOT, ".frames");
  await mkdir(dir, { recursive: true });
  const pool = await Promise.all(
    Array.from({ length: workers }, () => openPage(url)),
  );
  const { page } = pool[0];
  const { frames, fps } = await page.evaluate(() => ({
    frames: window.capture.frames,
    fps: window.capture.fps,
  }));

  const wav = await soundtrack(page, dir);

  const out = join(ROOT, opt.out);
  const enc = ffmpeg([
    ...[
      "-f",
      "rawvideo",
      "-pix_fmt",
      "rgba",
      "-s",
      `${W}x${H}`,
      "-r",
      String(fps),
      "-i",
      "-",
    ],
    ...["-i", wav],
    ...[
      "-vf",
      "vflip,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
    ],
    ...[
      "-c:v",
      "libx264",
      "-preset",
      "slow",
      "-crf",
      opt.crf,
      "-profile:v",
      "high",
    ],
    ...[
      "-colorspace",
      "bt709",
      "-color_primaries",
      "bt709",
      "-color_trc",
      "bt709",
    ],
    ...[
      "-c:a",
      "aac",
      "-b:a",
      "256k",
      "-movflags",
      "+faststart",
      "-shortest",
      out,
    ],
  ]);

  // Workers claim frames in order; a small window keeps them close together
  // while finished frames are written to ffmpeg strictly in sequence.
  const ready = new Map();
  let next = 0;
  let claim = 0;
  const started = Date.now();
  const flush = async () => {
    while (ready.has(next)) {
      const buf = ready.get(next);
      ready.delete(next);
      next++;
      if (!enc.p.stdin.write(buf)) await once(enc.p.stdin, "drain");
    }
  };
  await Promise.all(
    pool.map(async ({ page }) => {
      for (;;) {
        const i = claim++;
        if (i >= frames) return;
        while (i - next > workers * 3)
          await new Promise((r) => setTimeout(r, 15));
        const b64 = await page.evaluate(
          ([i, s]) => window.capture.frame(i, s),
          [i, samples],
        );
        ready.set(i, Buffer.from(b64, "base64"));
        await flush();
        if (i % 30 === 0) {
          const rate = (i + 1) / ((Date.now() - started) / 1000);
          process.stdout.write(
            `\rframe ${i}/${frames}  ${rate.toFixed(1)} fps  `,
          );
        }
      }
    }),
  );
  enc.p.stdin.end();
  await enc.done;
  process.stdout.write("\n");

  // Poster: the end card, full quality.
  const data = await page.evaluate(
    ([s]) => window.capture.still(14.4, s),
    [samples],
  );
  const png = join(dir, "poster.png");
  await writeFile(png, Buffer.from(data.split(",")[1], "base64"));
  const jpg = ffmpeg(["-i", png, "-q:v", "2", join(ROOT, "poster.jpg")]);
  jpg.p.stdin.end();
  await jpg.done;

  await Promise.all(pool.map(({ browser }) => browser.close()));
  console.log(`wrote ${out} in ${((Date.now() - started) / 1000).toFixed(0)}s`);
}

const { url, server } = await serve(opt.serve ? Number(opt.port) : 0);
if (opt.serve) {
  console.log(`serving ${url}`);
} else {
  const samples = Number(opt.samples);
  if (opt.audio) {
    const dir = join(ROOT, ".frames");
    await mkdir(dir, { recursive: true });
    const { browser, page } = await openPage(url);
    console.log(await soundtrack(page, dir));
    await browser.close();
  } else if (opt.stills)
    await stills(url, opt.stills.split(",").map(Number), samples);
  else await video(url, samples, Number(opt.workers));
  server.close();
}
