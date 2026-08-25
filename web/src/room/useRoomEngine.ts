import { useEffect } from "react";
import type { RefObject } from "react";
import { useStore } from "../state/store";
import {
  computeCamera,
  drawPings,
  drawWorld,
  readPalette,
  type Camera,
  type Palette,
  type Ping,
} from "./engine/render";
import {
  drawAgent,
  initRender,
  stepAgents,
  type RenderAgent,
} from "./engine/agents";
import { pickAgent, screenToWorld } from "./engine/input";
import type { Theme } from "../state/types";

export function useRoomEngine(canvasRef: RefObject<HTMLCanvasElement>): void {
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    const render: Map<string, RenderAgent> = initRender(
      useStore.getState().agents,
    );
    const pings: Ping[] = [];
    let cam: Camera = { scale: 1, offX: 0, offY: 0 };
    let dpr = 1;
    let cssW = 0;
    let cssH = 0;
    let pal: Palette = readPalette();
    let lastTheme: Theme = useStore.getState().theme;
    let lastEventCount = useStore.getState().events.length;
    let raf = 0;
    let last = performance.now();

    const resize = (): void => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const rect = parent.getBoundingClientRect();
      cssW = rect.width;
      cssH = rect.height;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
      cam = computeCamera(cssW, cssH);
    };

    const ro = new ResizeObserver(resize);
    if (canvas.parentElement) ro.observe(canvas.parentElement);
    resize();

    const onPointerDown = (e: PointerEvent): void => {
      const rect = canvas.getBoundingClientRect();
      const { x, y } = screenToWorld(
        cam,
        e.clientX - rect.left,
        e.clientY - rect.top,
      );
      const id = pickAgent(render, x, y);
      if (id) useStore.getState().select(id);
    };
    canvas.addEventListener("pointerdown", onPointerDown);

    const frame = (t: number): void => {
      const dt = Math.min((t - last) / 1000, 0.05);
      last = t;
      const snap = useStore.getState();

      if (snap.theme !== lastTheme) {
        lastTheme = snap.theme;
        pal = readPalette();
      }

      // emit a coordination ping at the manager whenever activity fires
      if (snap.events.length !== lastEventCount) {
        lastEventCount = snap.events.length;
        const mgr = render.get("octo");
        if (mgr && !reduceMotion) pings.push({ x: mgr.rx, y: mgr.ry, t: 0 });
      }

      stepAgents(render, snap.agents, dt);
      for (const p of pings) p.t += dt;
      for (let i = pings.length - 1; i >= 0; i--) {
        if (pings[i].t > 1) pings.splice(i, 1);
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);
      ctx.save();
      ctx.translate(cam.offX, cam.offY);
      ctx.scale(cam.scale, cam.scale);

      drawWorld(ctx, pal, snap.board, t);
      drawPings(ctx, pal, pings);

      const ordered = [...snap.agents].sort((a, b) => {
        const ra = render.get(a.id);
        const rb = render.get(b.id);
        return (ra ? ra.ry : a.posY) - (rb ? rb.ry : b.posY);
      });
      for (const a of ordered) {
        const r = render.get(a.id);
        if (r) drawAgent(ctx, pal, a, r, snap.selectedId, t, reduceMotion);
      }

      ctx.restore();
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      canvas.removeEventListener("pointerdown", onPointerDown);
    };
  }, [canvasRef]);
}
