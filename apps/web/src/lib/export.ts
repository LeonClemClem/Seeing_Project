/** Figure export: PNG of an SVG chart or a canvas, and animated GIF of canvas frames (small encoder, no
 * dependency: 256-colour palette from the most frequent colours, LZW). */

export function downloadBlob(blob: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

export function canvasToPng(canvas: HTMLCanvasElement, name: string) {
  canvas.toBlob((b) => b && downloadBlob(b, name), "image/png");
}

/* The hatch pattern of the Cn² convective levels lives in a hidden page-wide SVG (HatchDefs): copied into the
 * exported file so that the hatches survive. */
const HATCH =
  '<defs><pattern id="hh" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">' +
  '<rect width="3" height="6" fill="#fff"/><rect x="3" width="3" height="6" fill="#000"/></pattern></defs>';

/** PNG of an SVG chart (viewBox size x scale), on the panel colour. */
export function svgToPng(svg: SVGSVGElement, name: string, scale = 2, bg = "#111a2d"): Promise<void> {
  const vb = svg.viewBox.baseVal,
    w = Math.round((vb?.width || svg.clientWidth) * scale),
    h = Math.round((vb?.height || svg.clientHeight) * scale);
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(h));
  clone.removeAttribute("style");
  clone.insertAdjacentHTML(
    "afterbegin",
    `${HATCH}<style>text{font-family:'IBM Plex Sans',Arial,sans-serif}</style><rect x="${vb?.x ?? 0}" y="${vb?.y ?? 0}" width="${vb?.width ?? w}" height="${vb?.height ?? h}" fill="${bg}"/>`,
  );
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" }));
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = w;
      c.height = h;
      c.getContext("2d")!.drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      canvasToPng(c, name);
      resolve();
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("SVG export failed"));
    };
    img.src = url;
  });
}

/** Export the first SVG inside an element (the charts are rendered by SvgChart). */
export function exportSvgIn(el: Element | null, name: string) {
  const svg = el?.querySelector("svg");
  if (svg) void svgToPng(svg, name);
}

/** File-name friendly text. */
export const fileSafe = (s: string) =>
  s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^A-Za-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "");

/* ---------- animated GIF ---------- */

/** 256 colours: the most frequent 15-bit colours of all the frames (map colours are few: no banding). */
function palette(frames: ImageData[]): { pal: Uint8Array; index: (k: number) => number } {
  const count = new Uint32Array(32768);
  for (const f of frames)
    for (let p = 0; p < f.data.length; p += 4) count[((f.data[p]! >> 3) << 10) | ((f.data[p + 1]! >> 3) << 5) | (f.data[p + 2]! >> 3)]!++;
  const keys = [...count.keys()].filter((k) => count[k]! > 0).sort((a, b) => count[b]! - count[a]!).slice(0, 256);
  const pal = new Uint8Array(768);
  keys.forEach((k, i) => {
    pal[3 * i] = ((k >> 10) & 31) * 8 + 4;
    pal[3 * i + 1] = ((k >> 5) & 31) * 8 + 4;
    pal[3 * i + 2] = (k & 31) * 8 + 4;
  });
  const cache = new Int16Array(32768).fill(-1);
  const index = (k: number) => {
    const c = cache[k]!;
    if (c >= 0) return c;
    const r = ((k >> 10) & 31) * 8 + 4,
      g = ((k >> 5) & 31) * 8 + 4,
      b = (k & 31) * 8 + 4;
    let best = 0,
      bd = 1e9;
    for (let i = 0; i < keys.length; i++) {
      const d = (pal[3 * i]! - r) ** 2 + (pal[3 * i + 1]! - g) ** 2 + (pal[3 * i + 2]! - b) ** 2;
      if (d < bd) {
        bd = d;
        best = i;
      }
    }
    cache[k] = best;
    return best;
  };
  return { pal, index };
}

/** GIF LZW of 8-bit indices, as data sub-blocks. */
function lzw(px: Uint8Array, out: number[]) {
  const MIN = 8,
    CLEAR = 256,
    EOI = 257;
  let size = MIN + 1,
    next = EOI + 1,
    dict = new Map<number, number>(),
    acc = 0,
    nbits = 0;
  const block: number[] = [];
  const emit = (code: number) => {
    acc |= code << nbits;
    nbits += size;
    while (nbits >= 8) {
      block.push(acc & 255);
      acc >>>= 8;
      nbits -= 8;
      if (block.length === 255) {
        out.push(255, ...block);
        block.length = 0;
      }
    }
  };
  out.push(MIN);
  emit(CLEAR);
  let prefix = px[0]!;
  for (let i = 1; i < px.length; i++) {
    const k = px[i]!,
      key = (prefix << 8) | k,
      code = dict.get(key);
    if (code !== undefined) {
      prefix = code;
      continue;
    }
    emit(prefix);
    if (next < 4096) {
      dict.set(key, next++);
      if (next > 1 << size && size < 12) size++;
    } else {
      emit(CLEAR);
      dict = new Map();
      next = EOI + 1;
      size = MIN + 1;
    }
    prefix = k;
  }
  emit(prefix);
  emit(EOI);
  if (nbits > 0) block.push(acc & 255);
  if (block.length) out.push(block.length, ...block);
  out.push(0);
}

/** Looping animated GIF of same-size frames, `delayCs` hundredths of a second each. */
export function encodeGif(frames: ImageData[], delayCs = 90): Blob {
  const w = frames[0]!.width,
    h = frames[0]!.height,
    { pal, index } = palette(frames),
    out: number[] = [];
  const u16 = (v: number) => out.push(v & 255, (v >> 8) & 255);
  out.push(...[..."GIF89a"].map((c) => c.charCodeAt(0)));
  u16(w);
  u16(h);
  out.push(0xf7, 0, 0, ...pal);
  out.push(0x21, 0xff, 11, ...[..."NETSCAPE2.0"].map((c) => c.charCodeAt(0)), 3, 1, 0, 0, 0);
  for (const f of frames) {
    const px = new Uint8Array(w * h);
    for (let p = 0, i = 0; i < px.length; i++, p += 4)
      px[i] = index(((f.data[p]! >> 3) << 10) | ((f.data[p + 1]! >> 3) << 5) | (f.data[p + 2]! >> 3));
    out.push(0x21, 0xf9, 4, 0);
    u16(delayCs);
    out.push(0, 0, 0x2c);
    u16(0);
    u16(0);
    u16(w);
    u16(h);
    out.push(0);
    lzw(px, out);
  }
  out.push(0x3b);
  return new Blob([new Uint8Array(out)], { type: "image/gif" });
}
