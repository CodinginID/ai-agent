import type { Camera } from "./render";
import type { RenderAgent } from "./agents";

export interface WorldPoint {
  x: number;
  y: number;
}

export function screenToWorld(
  cam: Camera,
  sx: number,
  sy: number,
): WorldPoint {
  return {
    x: (sx - cam.offX) / cam.scale,
    y: (sy - cam.offY) / cam.scale,
  };
}

/** nearest agent within pick radius, using live render positions */
export function pickAgent(
  render: Map<string, RenderAgent>,
  wx: number,
  wy: number,
  radius = 26,
): string | null {
  let best: string | null = null;
  let bd = radius;
  for (const [id, r] of render) {
    const d = Math.hypot(r.rx - wx, r.ry - wy);
    if (d < bd) {
      bd = d;
      best = id;
    }
  }
  return best;
}
