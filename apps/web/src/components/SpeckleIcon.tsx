/** Loading icon: a star seen through turbulence. Short-exposure speckles computed for real, in a reduced form: a
 * Kolmogorov phase screen (power spectrum f^-11/3) blown across a circular pupil (frozen flow, tip-tilt removed so the
 * star stays centred), the image being |FFT(pupil x exp(i phase))|^2. D/r0 falls from 7 to 0 over the cycle, so the
 * speckles merge into an Airy pattern; strong stretch (^0.27) so that its rings show. One computation per frame, drawn
 * on every icon of the page; nothing runs when no icon is mounted. Reduced motion: the Airy pattern, still. */
import { useEffect, useRef } from "react";

const N = 128; // FFT grid
const W = 80; // image kept around the star (px of the canvas)
const DP = 18.5; // pupil diameter in grid px: lambda / D = N / DP ~ 6.9 px, first dark ring ~ 8.4 px
const S = 256; // phase screen (periodic)
const CYCLE_MS = 7000;
const DR0_MAX = 7;

function fft(re: Float64Array, im: Float64Array, n: number, inv: boolean) {
  for (let i = 1, j = 0; i < n; i++) {
    let b = n >> 1;
    for (; j & b; b >>= 1) j ^= b;
    j ^= b;
    if (i < j) {
      [re[i], re[j]] = [re[j]!, re[i]!];
      [im[i], im[j]] = [im[j]!, im[i]!];
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const a = ((inv ? 2 : -2) * Math.PI) / len,
      wr = Math.cos(a),
      wi = Math.sin(a);
    for (let i = 0; i < n; i += len) {
      let cr = 1,
        ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const p = i + k,
          q = p + len / 2,
          xr = re[q]! * cr - im[q]! * ci,
          xi = re[q]! * ci + im[q]! * cr;
        re[q] = re[p]! - xr;
        im[q] = im[p]! - xi;
        re[p] = re[p]! + xr;
        im[p] = im[p]! + xi;
        const t = cr * wr - ci * wi;
        ci = cr * wi + ci * wr;
        cr = t;
      }
    }
  }
}

function fft2(re: Float64Array, im: Float64Array, n: number, inv: boolean) {
  const r = new Float64Array(n),
    i2 = new Float64Array(n);
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) [r[x], i2[x]] = [re[y * n + x]!, im[y * n + x]!];
    fft(r, i2, n, inv);
    for (let x = 0; x < n; x++) [re[y * n + x], im[y * n + x]] = [r[x]!, i2[x]!];
  }
  for (let x = 0; x < n; x++) {
    for (let y = 0; y < n; y++) [r[y], i2[y]] = [re[y * n + x]!, im[y * n + x]!];
    fft(r, i2, n, inv);
    for (let y = 0; y < n; y++) [re[y * n + x], im[y * n + x]] = [r[y]!, i2[y]!];
  }
}

const gauss = () => {
  let u = 0;
  while (!u) u = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * Math.random());
};
const ease = (u: number) => (u < 0 ? 0 : u > 1 ? 1 : u * u * (3 - 2 * u));

type Engine = { screen: Float64Array; pupil: [number, number, number, number][]; norm: number };
let engine: Engine | null = null;

/** Phase in the pupil at the screen offset (ox, oy), piston and tip-tilt removed, and its rms. */
function pupilPhase(e: Engine, ox: number, oy: number): [Float64Array, number] {
  const ph = new Float64Array(e.pupil.length);
  let m = 0,
    sx = 0,
    sy = 0,
    sxx = 0,
    syy = 0;
  e.pupil.forEach(([x, y], k) => {
    const xs = (((Math.floor(ox) + x) % S) + S) % S,
      ys = (((Math.floor(oy) + y) % S) + S) % S;
    ph[k] = e.screen[ys * S + xs]!;
    m += ph[k]!;
  });
  m /= e.pupil.length;
  e.pupil.forEach(([, , dx, dy], k) => {
    ph[k] = ph[k]! - m;
    sx += ph[k]! * dx;
    sy += ph[k]! * dy;
    sxx += dx * dx;
    syy += dy * dy;
  });
  const ax = sx / sxx,
    ay = sy / syy;
  let v = 0;
  e.pupil.forEach(([, , dx, dy], k) => {
    ph[k] = ph[k]! - (ax * dx + ay * dy);
    v += ph[k]! ** 2;
  });
  return [ph, Math.sqrt(v / e.pupil.length)];
}

function makeEngine(): Engine {
  const re = new Float64Array(S * S),
    im = new Float64Array(S * S);
  for (let y = 0; y < S; y++)
    for (let x = 0; x < S; x++) {
      const f = Math.hypot(x < S / 2 ? x : x - S, y < S / 2 ? y : y - S),
        a = f ? Math.pow(f, -11 / 6) : 0;
      re[y * S + x] = gauss() * a;
      im[y * S + x] = gauss() * a;
    }
  fft2(re, im, S, true);
  const pupil: Engine["pupil"] = [];
  for (let y = 0; y < N; y++)
    for (let x = 0; x < N; x++) {
      const dx = x - N / 2 + 0.5,
        dy = y - N / 2 + 0.5;
      if (Math.hypot(dx, dy) <= DP / 2) pupil.push([x, y, dx, dy]);
    }
  const e: Engine = { screen: re, pupil, norm: 1 };
  let n = 0;
  for (let k = 0; k < 16; k++) n += pupilPhase(e, Math.random() * S, Math.random() * S)[1];
  e.norm = n / 16;
  return e;
}

const canvases = new Set<HTMLCanvasElement>();
let raf = 0,
  t0 = 0,
  ox = 0,
  oy = 0;
const fre = new Float64Array(N * N),
  fim = new Float64Array(N * N);
let pixels: ImageData | null = null;

/** Draw the star for D/r0 = dr0 (fade 0-1) on the given canvases. */
function draw(dr0: number, fade: number, targets: Iterable<HTMLCanvasElement>) {
  const e = (engine ??= makeEngine());
  const [ph] = pupilPhase(e, ox, oy),
    amp = (Math.sqrt(0.134) * Math.pow(dr0, 5 / 6)) / e.norm; // tilt-removed phase rms = sqrt(0.134) (D/r0)^(5/6)
  fre.fill(0);
  fim.fill(0);
  e.pupil.forEach(([x, y], k) => {
    const a = ph[k]! * amp,
      i = ((y + N / 2) % N) * N + ((x + N / 2) % N);
    fre[i] = Math.cos(a);
    fim[i] = Math.sin(a);
  });
  fft2(fre, fim, N, false);
  const off = (N - W) / 2,
    I = new Float32Array(W * W);
  let mx = 0;
  for (let y = 0; y < W; y++)
    for (let x = 0; x < W; x++) {
      const i = ((y + off + N / 2) % N) * N + ((x + off + N / 2) % N),
        v = fre[i]! ** 2 + fim[i]! ** 2;
      I[y * W + x] = v;
      if (v > mx) mx = v;
    }
  pixels ??= new ImageData(W, W);
  const d = pixels.data,
    C = W / 2;
  for (let i = 0; i < W * W; i++) {
    let v = Math.pow(I[i]! / mx, 0.27) * fade;
    const r = Math.hypot((i % W) + 0.5 - C, Math.floor(i / W) + 0.5 - C) / C;
    if (r > 0.94) v *= Math.max(0, (1 - r) / 0.06);
    d[4 * i] = Math.min(255, 255 * v * v * v);
    d[4 * i + 1] = Math.min(255, 255 * Math.pow(v, 1.25));
    d[4 * i + 2] = Math.min(255, 255 * 1.5 * Math.pow(v, 0.75));
    d[4 * i + 3] = 255 * Math.min(1, v * 2.5);
  }
  for (const c of targets) c.getContext("2d")!.putImageData(pixels, 0, 0);
}

/** Icons asked to finish (their data is ready): each goes quickly from where the cycle was to the Airy pattern,
 * holds it a moment, then calls its callback. */
const FINISH_MS = 550,
  HOLD_MS = 250;
const finishing = new Map<HTMLCanvasElement, { start: number; d0: number; f0: number; done: () => void }>();
let curDr0 = DR0_MAX,
  curFade = 1;

function frame(now: number) {
  if (!canvases.size && !finishing.size) {
    raf = 0;
    return;
  }
  if (!t0) t0 = now;
  const u = ((now - t0) % CYCLE_MS) / CYCLE_MS;
  ox += 0.9;
  oy += 0.35;
  curDr0 = DR0_MAX * (1 - ease((u - 0.12) / 0.5));
  curFade = u > 0.93 ? 1 - (u - 0.93) / 0.07 : u < 0.04 ? u / 0.04 : 1;
  if (canvases.size) draw(curDr0, curFade, canvases);
  finishing.forEach((f, c) => {
    const k = ease((now - f.start) / FINISH_MS);
    draw(f.d0 * (1 - k), f.f0 + (1 - f.f0) * k, [c]);
    if (now - f.start >= FINISH_MS + HOLD_MS) {
      finishing.delete(c);
      f.done();
    }
  });
  raf = requestAnimationFrame(frame);
}

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** `done`: the data is ready; the icon ends its cycle on the Airy pattern, then calls `onDone` (at once without a
 * canvas or with reduced motion). */
export function SpeckleIcon({ size = 40, done = false, onDone }: { size?: number; done?: boolean; onDone?: () => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const cb = useRef(onDone);
  cb.current = onDone;
  useEffect(() => {
    const c = ref.current;
    if (!c || !c.getContext("2d")) return; // no canvas (tests): nothing drawn
    canvases.add(c);
    if (reducedMotion()) draw(0, 1, [c]);
    else if (!raf) raf = requestAnimationFrame(frame);
    return () => {
      canvases.delete(c);
      finishing.delete(c);
    };
  }, []);
  useEffect(() => {
    if (!done) return;
    const c = ref.current;
    if (!c || !c.getContext("2d") || reducedMotion()) {
      cb.current?.();
      return;
    }
    canvases.delete(c);
    finishing.set(c, { start: performance.now(), d0: curDr0, f0: curFade, done: () => cb.current?.() });
    if (!raf) raf = requestAnimationFrame(frame);
  }, [done]);
  return <canvas ref={ref} width={W} height={W} aria-hidden="true" style={{ width: size, height: size, flex: "none" }} />;
}
