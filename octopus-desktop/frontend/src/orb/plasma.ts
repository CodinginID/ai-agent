import type { OrbState } from "./orbState";

// Parameter visual orb plasma per state — nilai persis dari mockup acuan
// (artifact "Octopus — Konsep UI Jarvis", issue #78).
export interface PlasmaStateParams {
  tint: [number, number, number];
  speed: number;
  swirl: number;
  radius: number;
  labelKey: string;
}

export const PLASMA_STATES: Record<OrbState, PlasmaStateParams> = {
  idle: { tint: [90, 200, 255], speed: 0.22, swirl: 0.7, radius: 92, labelKey: "orb_state_idle" },
  listening: { tint: [70, 230, 160], speed: 0.5, swirl: 1.0, radius: 100, labelKey: "orb_state_listening" },
  thinking: { tint: [255, 185, 90], speed: 1.3, swirl: 1.8, radius: 86, labelKey: "orb_state_thinking" },
  speaking: { tint: [120, 235, 255], speed: 0.7, swirl: 0.9, radius: 104, labelKey: "orb_state_speaking" },
};

export const PLASMA_PALETTE: ReadonlyArray<[number, number, number]> = [
  [130, 235, 255],
  [80, 160, 255],
  [55, 220, 210],
  [150, 205, 255],
  [110, 140, 255],
];

export interface PlasmaBlob {
  base: [number, number, number];
  ang: number;
  orbit: number;
  size: number;
  spd: number;
  phase: number;
}

export function makeBlobs(): PlasmaBlob[] {
  return PLASMA_PALETTE.map((c, i) => ({
    base: c,
    ang: (i / PLASMA_PALETTE.length) * Math.PI * 2,
    orbit: 0.24 + (i % 3) * 0.07,
    size: 0.8 + (i % 2) * 0.22,
    spd: 0.5 + i * 0.17,
    phase: i * 1.3,
  }));
}

export const lerp = (a: number, b: number, f: number): number => a + (b - a) * f;

export const mixColor = (
  a: [number, number, number],
  b: [number, number, number],
  f: number,
): [number, number, number] => [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)];
