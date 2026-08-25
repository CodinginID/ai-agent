import { AGENT_SPEED, center, ROLE, STATUS, zoneBy } from "./scene";
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

const MGR_HOME = center(zoneBy("Kantor Manajer"));

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
        r.wtx = MGR_HOME.x + rand(-70, 70);
        r.wty = MGR_HOME.y + rand(-30, 40);
      }
      tx = r.wtx;
      ty = r.wty;
    } else if (a.state === "idle") {
      r.wanderT -= dt;
      if (r.wanderT <= 0) {
        r.wanderT = rand(2.5, 6);
        if (Math.random() < 0.6) {
          r.wtx = a.homeX + rand(-46, 46);
          r.wty = a.homeY + rand(-38, 38);
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
