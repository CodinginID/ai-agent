import { AGENT_SPEED, getLayout, ROLE, STATUS } from "./scene";
import type { Agent } from "../../state/types";
import { mix, rrect, type Palette } from "./render";

export interface RenderAgent {
  rx: number;
  ry: number;
  dir: number;
  bob: number;
  /** cosmetic wander target (idle agents / manager patrol) */
  wtx: number;
  wty: number;
  wanderT: number;
}

const rand = (a: number, b: number): number => a + Math.random() * (b - a);

export function initRender(agents: Agent[]): Map<string, RenderAgent> {
  const m = new Map<string, RenderAgent>();
  for (const a of agents) {
    m.set(a.id, {
      rx: a.posX,
      ry: a.posY,
      dir: 1,
      bob: Math.random() * 6,
      wtx: a.homeX,
      wty: a.homeY,
      wanderT: rand(1, 4),
    });
  }
  return m;
}

/** Snap render positions to the store's logical positions — called by
 *  useRoomEngine right after a layout switch so agents don't visibly glide
 *  across the (now differently-sized) world. */
export function resetRenderPositions(
  render: Map<string, RenderAgent>,
  agents: Agent[],
): void {
  for (const a of agents) {
    const r = render.get(a.id);
    if (!r) continue;
    r.rx = a.posX;
    r.ry = a.posY;
    r.wtx = a.homeX;
    r.wty = a.homeY;
    r.wanderT = rand(1, 3);
  }
}

export function stepAgents(
  render: Map<string, RenderAgent>,
  agents: Agent[],
  dt: number,
): void {
  for (const a of agents) {
    let r = render.get(a.id);
    if (!r) {
      r = {
        rx: a.posX,
        ry: a.posY,
        dir: 1,
        bob: Math.random() * 6,
        wtx: a.homeX,
        wty: a.homeY,
        wanderT: rand(1, 4),
      };
      render.set(a.id, r);
    }

    // decide the point this avatar walks toward
    let tx: number;
    let ty: number;
    if (a.role === "manager") {
      r.wanderT -= dt;
      if (r.wanderT <= 0) {
        r.wanderT = rand(3, 6);
        // Portrait: zona kecil (tile 40px + pill) → jelajah manajer dipersempit.
        const k = getLayout().kind === "portrait" ? 0.3 : 1;
        r.wtx = a.homeX + rand(-70, 70) * k;
        r.wty = a.homeY + rand(-30, 40) * k;
      }
      tx = r.wtx;
      ty = r.wty;
    } else if (a.state === "idle") {
      r.wanderT -= dt;
      if (r.wanderT <= 0) {
        r.wanderT = rand(2.5, 6);
        if (Math.random() < 0.6) {
          const k = getLayout().kind === "portrait" ? 0.25 : 1;
          r.wtx = a.homeX + rand(-46, 46) * k;
          r.wty = a.homeY + rand(-38, 38) * k;
        }
      }
      tx = r.wtx;
      ty = r.wty;
    } else {
      tx = a.targetX;
      ty = a.targetY;
    }

    const dx = tx - r.rx;
    const dy = ty - r.ry;
    const d = Math.hypot(dx, dy);
    if (d > 1) {
      const step = Math.min(d, AGENT_SPEED * dt);
      r.rx += (dx / d) * step;
      r.ry += (dy / d) * step;
      if (Math.abs(dx) > 1) r.dir = dx > 0 ? 1 : -1;
    }
    r.bob += dt;
  }
}

export function drawAgent(
  ctx: CanvasRenderingContext2D,
  pal: Palette,
  a: Agent,
  r: RenderAgent,
  selectedId: string | null,
  timeMs: number,
  reduceMotion: boolean,
): void {
  if (getLayout().kind === "portrait") {
    drawAgentTile(ctx, pal, a, r, selectedId);
    return;
  }
  drawAgentCircle(ctx, pal, a, r, selectedId, timeMs, reduceMotion);
}

/** Portrait "Ruangan" tab avatar — a 40×40 rounded-square tile filled with
 *  the role color, a status-colored ring, the role's emoji icon, and a name
 *  pill underneath (matches the approved mockup). */
function drawAgentTile(
  ctx: CanvasRenderingContext2D,
  pal: Palette,
  a: Agent,
  r: RenderAgent,
  selectedId: string | null,
): void {
  const size = 40;
  const half = size / 2;
  const x = r.rx;
  const y = r.ry;
  const st = STATUS[a.state] ?? STATUS.idle;
  const ringColor = pal[st.c];

  // selection highlight (drawn first, sits outside everything else)
  if (a.id === selectedId) {
    ctx.lineWidth = 2;
    ctx.strokeStyle = pal.ping;
    rrect(ctx, x - half - 5, y - half - 5, size + 10, size + 10, 15);
    ctx.stroke();
  }

  // tile body + drop shadow
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,.38)";
  ctx.shadowBlur = 14;
  ctx.shadowOffsetY = 4;
  ctx.fillStyle = ROLE[a.role].color;
  rrect(ctx, x - half, y - half, size, size, 12);
  ctx.fill();
  ctx.restore();

  // status ring — sits just outside the tile edge (mirrors the mockup's
  // outward box-shadow ring) instead of overlapping the icon.
  const ringPad = 1.5;
  ctx.lineWidth = 3;
  ctx.strokeStyle = ringColor;
  rrect(ctx, x - half - ringPad, y - half - ringPad, size + ringPad * 2, size + ringPad * 2, 12 + ringPad);
  ctx.stroke();

  // role icon
  ctx.font = '18px "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif';
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(ROLE[a.role].icon, x, y + 1);

  // name pill
  ctx.font = "500 10.5px 'IBM Plex Sans', sans-serif";
  const pw = ctx.measureText(a.name).width + 14;
  const py = y + half + 6;
  ctx.fillStyle = pal.nameBg;
  rrect(ctx, x - pw / 2, py, pw, 17, 99);
  ctx.fill();
  ctx.fillStyle = pal.name;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(a.name, x, py + 8.5);
}

/** Landscape (desktop) avatar — unchanged circle+eyes body. */
function drawAgentCircle(
  ctx: CanvasRenderingContext2D,
  pal: Palette,
  a: Agent,
  r: RenderAgent,
  selectedId: string | null,
  timeMs: number,
  reduceMotion: boolean,
): void {
  const radius = a.role === "manager" ? 19 : 16;
  const bob = reduceMotion ? 0 : Math.sin(r.bob * 3) * 1;
  const col = ROLE[a.role].color;
  const st = STATUS[a.state] ?? STATUS.idle;
  const x = r.rx;
  const y = r.ry + bob;

  // shadow
  ctx.fillStyle = pal.shadow;
  ctx.beginPath();
  ctx.ellipse(x, r.ry + radius * 0.72, radius * 0.82, radius * 0.34, 0, 0, Math.PI * 2);
  ctx.fill();

  // selection ring
  if (a.id === selectedId) {
    ctx.beginPath();
    ctx.arc(x, y, radius + 6, 0, Math.PI * 2);
    ctx.strokeStyle = pal.ping;
    ctx.lineWidth = 2.5;
    ctx.stroke();
  }
  // approval pulse ring
  if (a.state === "await") {
    const pr = radius + 6 + (reduceMotion ? 0 : Math.sin(timeMs / 240) * 3 + 3);
    ctx.beginPath();
    ctx.arc(x, y, pr, 0, Math.PI * 2);
    ctx.strokeStyle = pal.approval;
    ctx.lineWidth = 2.5;
    ctx.globalAlpha = 0.85;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  // body
  const grad = ctx.createLinearGradient(x, y - radius, x, y + radius);
  grad.addColorStop(0, mix(col, "#ffffff", 0.22));
  grad.addColorStop(1, col);
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();
  if (a.role === "manager") {
    ctx.strokeStyle = mix(col, "#ffffff", 0.35);
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // eyes (direction)
  const ex = r.dir * 4;
  ctx.fillStyle = "rgba(255,255,255,.9)";
  ctx.beginPath();
  ctx.arc(x + ex - 3.5, y - 2, 2.1, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(x + ex + 3.5, y - 2, 2.1, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "rgba(0,0,0,.65)";
  ctx.beginPath();
  ctx.arc(x + ex - 3.5, y - 2, 1, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(x + ex + 3.5, y - 2, 1, 0, Math.PI * 2);
  ctx.fill();

  // status pill
  const label = st.txt;
  ctx.font = "600 11px 'IBM Plex Mono', monospace";
  const pw = ctx.measureText(label).width + 18;
  const py = y - radius - 17;
  ctx.fillStyle = pal.nameBg;
  rrect(ctx, x - pw / 2, py, pw, 15, 7.5);
  ctx.fill();
  ctx.fillStyle = pal[st.c];
  ctx.beginPath();
  ctx.arc(x - pw / 2 + 8, py + 7.5, 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = pal.name;
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText(label, x - pw / 2 + 14, py + 8);

  // working progress arc
  if (a.state === "working" || a.state === "review") {
    ctx.beginPath();
    ctx.arc(x, y, radius + 3.5, -Math.PI / 2, -Math.PI / 2 + a.progress * Math.PI * 2);
    ctx.strokeStyle = pal.work;
    ctx.lineWidth = 2.5;
    ctx.stroke();
  }

  // name
  ctx.font = "600 12px 'IBM Plex Sans', sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillStyle = pal.name;
  ctx.fillText(a.name, x, y + radius + 4);
}
