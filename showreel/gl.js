// WebGL2 compositor. Each output frame averages several sub-frame renders in
// a half-float buffer (true motion blur from a 180 degree shutter), shades the
// liquid scene's metaballs, then finishes with bloom, vignette and grain.
// Bloom runs at 1/8 resolution so a frame stays cheap even on a software GPU.

const VERT = `#version 300 es
in vec2 aPos;
out vec2 vUv;
void main() {
  vUv = aPos * 0.5 + 0.5;
  gl_Position = vec4(aPos, 0.0, 1.0);
}`;

const SCENE = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
uniform sampler2D uLayer;
uniform vec2 uRes;
uniform vec3 uBg;
uniform float uWeight;
uniform float uCA;
uniform int uCount;
uniform vec3 uBalls[12];
uniform vec3 uLit;
uniform vec3 uShade;
uniform vec3 uRim;

float field(vec2 p, out vec2 grad) {
  float f = 0.0;
  grad = vec2(0.0);
  for (int i = 0; i < 12; i++) {
    if (i >= uCount) break;
    vec2 d = p - uBalls[i].xy;
    float dd = dot(d, d) + 1.0;
    float k = uBalls[i].z * uBalls[i].z / dd;
    f += k;
    grad -= 2.0 * k / dd * d;
  }
  return f;
}

void main() {
  // The 2D layer is uploaded top row first; flip here instead of on upload.
  vec2 uv = vec2(vUv.x, 1.0 - vUv.y);
  vec2 px = uv * uRes;
  vec3 col = uBg;
  if (uCount > 0) {
    vec2 gs;
    float fs = field(px - vec2(22.0, 34.0), gs);
    col *= 1.0 - 0.3 * smoothstep(0.25, 1.15, fs);
    vec2 g;
    float f = field(px, g);
    float w = fwidth(f) * 1.1 + 1e-4;
    float m = smoothstep(1.0 - w, 1.0 + w, f);
    // Height field h = sqrt(1 - 1/f): exactly a hemisphere for a lone ball
    // (f = r^2/d^2), and a smooth pillow where balls merge, so the shading
    // stays continuous through every split and join.
    float inv = 1.0 / max(f, 1e-4);
    float h = sqrt(max(0.0, 1.0 - inv));
    vec2 gh = g * inv * inv / (2.0 * max(h, 0.04));
    vec3 n = normalize(vec3(-gh * 75.0, 1.0));
    vec3 L = normalize(vec3(-0.5, -0.62, 0.6));
    vec3 Hv = normalize(L + vec3(0.0, 0.0, 1.0));
    float diff = clamp(dot(n, L), 0.0, 1.0);
    float nh = clamp(dot(n, Hv), 0.0, 1.0);
    float spec = pow(nh, 80.0) + 0.18 * pow(nh, 10.0);
    float rim = pow(1.0 - n.z, 2.0);
    vec3 blob = mix(uShade, uLit, 0.2 + 0.8 * diff);
    blob += rim * uRim * 0.55 + spec * 0.85;
    col = mix(col, blob, m);
  }
  vec4 layer = texture(uLayer, uv);
  vec3 lay = layer.rgb;
  if (uCA > 0.0005) {
    vec2 off = (uv - 0.5) * uCA;
    lay.r = texture(uLayer, uv + off).r;
    lay.b = texture(uLayer, uv - off).b;
  }
  col = col * (1.0 - layer.a) + lay;
  outColor = vec4(col * uWeight, uWeight);
}`;

// Box-filter the frame down 8x, keeping only what is bright enough to glow.
const DOWN = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
uniform sampler2D uSrc;
uniform vec2 uTexel;
void main() {
  vec3 c = vec3(0.0);
  for (int y = 0; y < 4; y++) {
    for (int x = 0; x < 4; x++) {
      vec2 o = (vec2(float(x), float(y)) * 2.0 - 3.0) * uTexel;
      c += texture(uSrc, vUv + o).rgb;
    }
  }
  c /= 16.0;
  float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
  outColor = vec4(c * smoothstep(0.12, 0.7, l), 1.0);
}`;

const BLUR = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
uniform sampler2D uSrc;
uniform vec2 uStep;
void main() {
  float w[7] = float[](0.1964, 0.1748, 0.1232, 0.0689, 0.0305, 0.0107, 0.0030);
  vec3 c = texture(uSrc, vUv).rgb * w[0];
  for (int i = 1; i < 7; i++) {
    vec2 o = uStep * float(i);
    c += (texture(uSrc, vUv + o).rgb + texture(uSrc, vUv - o).rgb) * w[i];
  }
  outColor = vec4(c, 1.0);
}`;

const FINAL = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
uniform sampler2D uAccum;
uniform sampler2D uGlow;
uniform vec2 uRes;
uniform float uGrain;
uniform float uVignette;
uniform float uBloom;
uniform float uFlash;
uniform float uNoiseOffset;

float hash12(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

void main() {
  vec3 c = texture(uAccum, vUv).rgb;
  if (uBloom > 0.0) c += texture(uGlow, vUv).rgb * uBloom * 1.6;
  c = mix(c, vec3(1.0, 0.97, 0.93), uFlash);
  vec2 q = vUv - 0.5;
  q.x *= uRes.x / uRes.y;
  c *= 1.0 - uVignette * smoothstep(0.3, 1.15, length(q));
  vec2 fc = gl_FragCoord.xy;
  float n = hash12(fc + uNoiseOffset * 97.31) + hash12(fc.yx * 1.31 + uNoiseOffset * 13.7) - 1.0;
  c += n * uGrain;
  outColor = vec4(c, 1.0);
}`;

function program(gl, fs) {
  const compile = (type, src) => {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(sh));
    }
    return sh;
  };
  const p = gl.createProgram();
  gl.attachShader(p, compile(gl.VERTEX_SHADER, VERT));
  gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fs));
  gl.bindAttribLocation(p, 0, "aPos");
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(p));
  }
  const u = {};
  const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) {
    const name = gl.getActiveUniform(p, i).name.replace("[0]", "");
    u[name] = gl.getUniformLocation(p, name);
  }
  return { p, u };
}

function target(gl, w, h) {
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGBA16F, w, h);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  const fbo = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(
    gl.FRAMEBUFFER,
    gl.COLOR_ATTACHMENT0,
    gl.TEXTURE_2D,
    tex,
    0,
  );
  return { tex, fbo, w, h };
}

const toUnit = (c) => c.map((v) => v / 255);

export class Compositor {
  constructor(canvas, width, height) {
    this.w = width;
    this.h = height;
    canvas.width = width;
    canvas.height = height;
    const gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: false,
      preserveDrawingBuffer: true,
    });
    if (!gl) throw new Error("WebGL2 is required");
    if (!gl.getExtension("EXT_color_buffer_float")) {
      throw new Error("EXT_color_buffer_float is required");
    }
    this.gl = gl;
    this.scene = program(gl, SCENE);
    this.down = program(gl, DOWN);
    this.blur = program(gl, BLUR);
    this.final = program(gl, FINAL);

    const quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
      gl.STATIC_DRAW,
    );
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    this.layer = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.layer);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    this.accum = target(gl, width, height);
    const gw = Math.ceil(width / 8);
    const gh = Math.ceil(height / 8);
    this.glowA = target(gl, gw, gh);
    this.glowB = target(gl, gw, gh);
  }

  pass(prog, out, bind) {
    const { gl } = this;
    gl.bindFramebuffer(gl.FRAMEBUFFER, out ? out.fbo : null);
    gl.viewport(0, 0, out ? out.w : this.w, out ? out.h : this.h);
    gl.useProgram(prog.p);
    bind(prog.u);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  begin() {
    const { gl } = this;
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.accum.fbo);
    gl.viewport(0, 0, this.w, this.h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
  }

  add(source, fx, weight) {
    const { gl } = this;
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.layer);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    this.pass(this.scene, this.accum, (u) => {
      gl.uniform1i(u.uLayer, 0);
      gl.uniform2f(u.uRes, this.w, this.h);
      gl.uniform3fv(u.uBg, toUnit(fx.bg));
      gl.uniform1f(u.uWeight, weight);
      gl.uniform1f(u.uCA, fx.ca);
      const balls = fx.balls ?? [];
      gl.uniform1i(u.uCount, balls.length);
      if (balls.length) {
        gl.uniform3fv(u.uBalls, balls.flat());
        gl.uniform3fv(u.uLit, fx.lit);
        gl.uniform3fv(u.uShade, fx.shade);
        gl.uniform3fv(u.uRim, fx.rim);
      }
    });
    gl.disable(gl.BLEND);
  }

  end(fx, seed) {
    const { gl, accum, glowA, glowB } = this;
    gl.activeTexture(gl.TEXTURE0);
    if (fx.bloom > 0) {
      gl.bindTexture(gl.TEXTURE_2D, accum.tex);
      this.pass(this.down, glowA, (u) => {
        gl.uniform1i(u.uSrc, 0);
        gl.uniform2f(u.uTexel, 1 / accum.w, 1 / accum.h);
      });
      for (const [src, dst, sx, sy] of [
        [glowA, glowB, 1.5, 0],
        [glowB, glowA, 0, 1.5],
      ]) {
        gl.bindTexture(gl.TEXTURE_2D, src.tex);
        this.pass(this.blur, dst, (u) => {
          gl.uniform1i(u.uSrc, 0);
          gl.uniform2f(u.uStep, sx / src.w, sy / src.h);
        });
      }
    }
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, glowA.tex);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, accum.tex);
    this.pass(this.final, null, (u) => {
      gl.uniform1i(u.uAccum, 0);
      gl.uniform1i(u.uGlow, 1);
      gl.uniform2f(u.uRes, this.w, this.h);
      gl.uniform1f(u.uGrain, fx.grain);
      gl.uniform1f(u.uVignette, fx.vignette);
      gl.uniform1f(u.uBloom, fx.bloom);
      gl.uniform1f(u.uFlash, fx.flash);
      gl.uniform1f(u.uNoiseOffset, seed % 1000);
    });
  }
}
