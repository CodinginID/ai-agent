import { getLayout, isRackZone, type Zone } from "./scene";
import type { BoardCard } from "../../state/types";
import { drawBoard } from "./board";

export interface Palette {
  floor: string;
  floorLine: string;
  wall: string;
  zone: string;
  zoneLine: string;
  zoneLabel: string;
  shadow: string;
  server: string;
  name: string;
  nameBg: string;
  ping: string;
  idle: string;
  work: string;
  approval: string;
  review: string;
  done: string;
  error: string;
}

export interface Camera {
  scale: number;
  offX: number;
  offY: number;
}

export interface Ping {
  x: number;
  y: number;
  t: number;
}

export function readPalette(): Palette {
  const s = getComputedStyle(document.documentElement);
  const g = (n: string): string => s.getPropertyValue(n).trim();
  return {
    floor: g("--c-floor"),
    floorLine: g("--c-floor-line"),
    wall: g("--c-wall"),
    zone: g("--c-zone"),
    zoneLine: g("--c-zone-line"),
    zoneLabel: g("--c-zonelabel"),
    shadow: g("--c-shadow"),
    server: g("--c-server"),
    name: g("--c-name"),
    nameBg: g("--c-namebg"),
    ping: g("--c-ping"),
    idle: g("--st-idle"),
    work: g("--st-work"),
    approval: g("--st-approval"),
    review: g("--st-review"),
    done: g("--st-done"),
    error: g("--st-error"),
  };
}

export function computeCamera(cssW: number, cssH: number): Camera {
  const layout = getLayout();
  if (layout.kind === "portrait") {
    // Fit width exactly (the mockup room is a fixed 390-wide grid); if the
    // world is taller than the container, allow vertical drag-pan instead
    // of shrinking to fit (see clampOffY + useRoomEngine's pointer drag).
    const scale = cssW / layout.worldW;
    return { scale, offX: 0, offY: 0 };
  }
  const pad = 24;
  const scale = Math.min(
    (cssW - pad * 2) / layout.worldW,
    (cssH - pad * 2) / layout.worldH,
  );
  return {
    scale,
    offX: (cssW - layout.worldW * scale) / 2,
    offY: (cssH - layout.worldH * scale) / 2,
  };
}

/** Batasi pan horizontal (landscape) supaya tepi world tak lepas dari layar. */
export function clampOffX(offX: number, cssW: number, scale: number): number {
  const pad = 24;
  const worldW = getLayout().worldW;
  const minX = cssW - worldW * scale - pad;
  const maxX = pad;
  if (minX > maxX) return (cssW - worldW * scale) / 2; // world lebih sempit: tengah
  return Math.min(maxX, Math.max(minX, offX));
}

/** Batasi pan vertikal (portrait) — 0 kalau world muat, else clamp supaya
 *  tepi atas/bawah tak lepas dari layar. */
export function clampOffY(offY: number, cssH: number, scale: number): number {
  const worldH = getLayout().worldH;
  const worldHpx = worldH * scale;
  if (worldHpx <= cssH) return 0;
  const minY = cssH - worldHpx;
  const maxY = 0;
  return Math.min(maxY, Math.max(minY, offY));
}

export function rrect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  // arcTo dengan r > setengah sisi menghasilkan busur raksasa (bukan di-clamp
  // seperti CSS border-radius) → fill/stroke "menyebar" ke luar bentuk.
  r = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function hex(h: string): [number, number, number] {
  const c = h.replace("#", "");
  return [
    parseInt(c.slice(0, 2), 16),
    parseInt(c.slice(2, 4), 16),
    parseInt(c.slice(4, 6), 16),
  ];
}

export function mix(a: string, b: string, t: number): string {
  const pa = hex(a);
  const pb = hex(b);
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function drawServer(ctx: CanvasRenderingContext2D, pal: Palette, z: Zone, timeMs: number): void {
  const n = 3;
  const gap = 14;
  const rw = (z.w - gap * (n + 1)) / n;
  for (let i = 0; i < n; i++) {
    const rx = z.x + gap + i * (rw + gap);
    const ry = z.y + 40;
    const rh = z.h - 70;
    ctx.fillStyle = pal.wall;
    rrect(ctx, rx, ry, rw, rh, 6);
    ctx.fill();
    for (let j = 0; j < 5; j++) {
      const on = ((timeMs / 400 + i * 2 + j) | 0) % 3 === 0;
      ctx.fillStyle = on ? pal.done : pal.floorLine;
      ctx.beginPath();
      ctx.arc(rx + 12, ry + 16 + (j * (rh - 30)) / 4, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

export function drawWorld(
  ctx: CanvasRenderingContext2D,
  pal: Palette,
  board: BoardCard[],
  timeMs: number,
): void {
  const layout = getLayout();
  const portrait = layout.kind === "portrait";
  const gridStep = portrait ? 32 : 40;

  // floor (+ wall border band, landscape only — mockup has no such band)
  if (!portrait) {
    ctx.fillStyle = pal.wall;
    rrect(ctx, -16, -16, layout.worldW + 32, layout.worldH + 32, 26);
    ctx.fill();
  }
  ctx.fillStyle = pal.floor;
  if (portrait) {
    ctx.fillRect(0, 0, layout.worldW, layout.worldH);
  } else {
    rrect(ctx, 0, 0, layout.worldW, layout.worldH, 18);
    ctx.fill();
  }

  // floor grid (clipped)
  ctx.strokeStyle = pal.floorLine;
  ctx.lineWidth = 1;
  ctx.save();
  if (portrait) {
    ctx.beginPath();
    ctx.rect(0, 0, layout.worldW, layout.worldH);
  } else {
    rrect(ctx, 0, 0, layout.worldW, layout.worldH, 18);
  }
  ctx.clip();
  for (let x = gridStep; x < layout.worldW; x += gridStep) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, layout.worldH);
    ctx.stroke();
  }
  for (let y = gridStep; y < layout.worldH; y += gridStep) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(layout.worldW, y);
    ctx.stroke();
  }
  ctx.restore();

  // zones
  for (const z of layout.zones) {
    const isServer = isRackZone(z);
    ctx.fillStyle = isServer ? pal.server : pal.zone;
    ctx.strokeStyle = pal.zoneLine;
    ctx.lineWidth = 1.5;
    rrect(ctx, z.x, z.y, z.w, z.h, 14);
    ctx.fill();
    ctx.stroke();
    if (isServer) drawServer(ctx, pal, z, timeMs);
    ctx.fillStyle = pal.zoneLabel;
    if (portrait) {
      ctx.font = "500 10px 'IBM Plex Mono', monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(z.name.toUpperCase(), z.x + 10, z.y + 8);
    } else {
      ctx.font = "600 13px 'Chakra Petch', sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(z.name.toUpperCase(), z.x + 12, z.y + 11);
    }
  }

  // kanban board: drawn inside a landscape zone — no room for it in the
  // compact portrait grid (mockup has no board either).
  if (!portrait) drawBoard(ctx, pal, board);
}

export function drawPings(
  ctx: CanvasRenderingContext2D,
  pal: Palette,
  pings: Ping[],
): void {
  for (const p of pings) {
    const rr = 8 + p.t * 46;
    const al = (1 - p.t) * 0.5;
    ctx.beginPath();
    ctx.arc(p.x, p.y, rr, 0, Math.PI * 2);
    ctx.strokeStyle = pal.ping;
    ctx.globalAlpha = al;
    ctx.lineWidth = 2.5;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
}
