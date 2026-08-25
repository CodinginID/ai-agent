import { BOARD_COLS, ROLE } from "./scene";
import type { BoardCard } from "../../state/types";
import type { Palette } from "./render";
import { rrect } from "./render";

function trunc(
  ctx: CanvasRenderingContext2D,
  s: string,
  wpx: number,
): string {
  ctx.font = "500 9px 'IBM Plex Sans', sans-serif";
  if (ctx.measureText(s).width <= wpx) return s;
  let r = s;
  while (r.length > 1 && ctx.measureText(r + "…").width > wpx) {
    r = r.slice(0, -1);
  }
  return r + "…";
}

export function drawBoard(
  ctx: CanvasRenderingContext2D,
  pal: Palette,
  cards: BoardCard[],
): void {
  const b = { x: 800, y: 36, w: 446, h: 158 };
  ctx.fillStyle = pal.zone;
  ctx.strokeStyle = pal.zoneLine;
  ctx.lineWidth = 1.5;
  rrect(ctx, b.x, b.y, b.w, b.h, 12);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = pal.zoneLabel;
  ctx.font = "600 12px 'Chakra Petch', sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillText("📌 PAPAN TUGAS", b.x + 12, b.y + 9);

  const top = b.y + 30;
  const pad = 10;
  const cols = BOARD_COLS.length;
  const cw = (b.w - pad * (cols + 1)) / cols;

  BOARD_COLS.forEach((col, ci) => {
    const cx = b.x + pad + ci * (cw + pad);
    ctx.fillStyle = pal.floor;
    rrect(ctx, cx, top, cw, b.h - 40, 8);
    ctx.fill();
    ctx.fillStyle = pal.zoneLabel;
    ctx.font = "600 9px 'IBM Plex Mono', monospace";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText(col.t.toUpperCase(), cx + 7, top + 6);

    const inCol = cards.filter((c) => c.col === col.k);
    const maxShow = 4;
    let cy = top + 20;
    inCol.slice(0, maxShow).forEach((c) => {
      const ch = 22;
      ctx.globalAlpha = c.col === "done" ? Math.max(0.4, 1 - c.doneT / 6) : 1;
      ctx.fillStyle = pal.zone;
      ctx.strokeStyle = pal.zoneLine;
      ctx.lineWidth = 1;
      rrect(ctx, cx + 5, cy, cw - 10, ch, 5);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = ROLE[c.role] ? ROLE[c.role].color : pal.work;
      ctx.beginPath();
      ctx.arc(cx + 12, cy + ch / 2, 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = pal.name;
      ctx.font = "500 9px 'IBM Plex Sans', sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(trunc(ctx, c.desc, cw - 26), cx + 19, cy + ch / 2);
      ctx.globalAlpha = 1;
      cy += ch + 4;
    });
    if (inCol.length > maxShow) {
      ctx.fillStyle = pal.zoneLabel;
      ctx.font = "500 9px 'IBM Plex Mono', monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(`+${inCol.length - maxShow} lagi`, cx + 7, cy + 2);
    }
  });
}
