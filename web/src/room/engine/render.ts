import { WORLD_H, WORLD_W, ZONES, type Zone } from "./scene";
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
  const pad = 24;
  // Portrait (HP): world 1280×800 di-"contain" akan jadi strip kecil di tengah
  // → pakai mode cover: skala ke tinggi kontainer, lebar boleh meluap dan
  // di-pan horizontal (lihat useRoomEngine). Awal: pusat world di tengah layar.
  if (cssH > cssW * (WORLD_H / WORLD_W) * 1.35) {
    const scale = (cssH - pad * 2) / WORLD_H;
    return {
      scale,
      offX: clampOffX((cssW - WORLD_W * scale) / 2, cssW, scale),
      offY: pad,
    };
  }
  const scale = Math.min(
    (cssW - pad * 2) / WORLD_W,
    (cssH - pad * 2) / WORLD_H,
  );
  return {
    scale,
    offX: (cssW - WORLD_W * scale) / 2,
    offY: (cssH - WORLD_H * scale) / 2,
  };
}

/** Batasi pan horizontal supaya tepi world tak lepas dari layar (mode cover). */
export function clampOffX(offX: number, cssW: number, scale: number): number {
  const pad = 24;
  const minX = cssW - WORLD_W * scale - pad;
  const maxX = pad;
  if (minX > maxX) return (cssW - WORLD_W * scale) / 2; // world lebih sempit: tengah
  return Math.min(maxX, Math.max(minX, offX));
}

export function rrect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
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
  // floor + wall
  ctx.fillStyle = pal.wall;
  rrect(ctx, -16, -16, WORLD_W + 32, WORLD_H + 32, 26);
  ctx.fill();
  ctx.fillStyle = pal.floor;
  rrect(ctx, 0, 0, WORLD_W, WORLD_H, 18);
  ctx.fill();

  // floor grid (clipped)
  ctx.strokeStyle = pal.floorLine;
  ctx.lineWidth = 1;
  ctx.save();
  rrect(ctx, 0, 0, WORLD_W, WORLD_H, 18);
  ctx.clip();
  for (let x = 40; x < WORLD_W; x += 40) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, WORLD_H);
    ctx.stroke();
  }
  for (let y = 40; y < WORLD_H; y += 40) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(WORLD_W, y);
    ctx.stroke();
  }
  ctx.restore();

  // zones
  for (const z of ZONES) {
    const isServer = z.name === "Server Room";
    ctx.fillStyle = isServer ? pal.server : pal.zone;
    ctx.strokeStyle = pal.zoneLine;
    ctx.lineWidth = 1.5;
    rrect(ctx, z.x, z.y, z.w, z.h, 14);
    ctx.fill();
    ctx.stroke();
    if (isServer) drawServer(ctx, pal, z, timeMs);
    ctx.fillStyle = pal.zoneLabel;
    ctx.font = "600 13px 'Chakra Petch', sans-serif";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText(z.name.toUpperCase(), z.x + 12, z.y + 11);
  }

  drawBoard(ctx, pal, board);
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
