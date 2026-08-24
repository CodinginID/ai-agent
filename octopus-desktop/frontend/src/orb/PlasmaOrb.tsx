import { useEffect, useRef } from "react";
import type { OrbState } from "./orbState";
import { lerp, makeBlobs, mixColor, PLASMA_STATES } from "./plasma";

export interface PlasmaOrbProps {
  state: OrbState;
  amplitude?: number;
  paused?: boolean;
  size?: number;
}

// Orb plasma 2D-canvas ala Siri — port langsung dari mockup acuan #78:
// halo + gradien dasar + 5 blob additive yang berputar + specular highlight
// + dua cincin HUD arc bertitik yang ikut warna state.
export function PlasmaOrb({ state, amplitude = 0, paused = false, size = 420 }: PlasmaOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef(state);
  const ampRef = useRef(amplitude);
  stateRef.current = state;
  ampRef.current = amplitude;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * DPR;
    canvas.height = size * DPR;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.scale(DPR, DPR);

    const cx = size / 2;
    const cy = size / 2;
    const scale = size / 420; // parameter mockup dikalibrasi untuk 420px
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const blobs = makeBlobs();

    let t = 0;
    let swirlAcc = 0;
    let amp = 0;
    const cur = {
      tint: [...PLASMA_STATES.idle.tint] as [number, number, number],
      speed: PLASMA_STATES.idle.speed,
      swirl: PLASMA_STATES.idle.swirl,
      radius: PLASMA_STATES.idle.radius,
    };

    function ring(radius: number, a0: number, a1: number, rot: number, alpha: number, tickN: number, tint: number[]) {
      if (!ctx) return;
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(rot);
      ctx.lineWidth = 1;
      ctx.strokeStyle = `rgba(${tint[0]},${tint[1]},${tint[2]},${alpha})`;
      ctx.beginPath();
      ctx.arc(0, 0, radius, a0, a1);
      ctx.stroke();
      for (let k = 0; k <= tickN; k++) {
        const ang = a0 + (a1 - a0) * (k / tickN);
        ctx.beginPath();
        ctx.moveTo(Math.cos(ang) * (radius - 3), Math.sin(ang) * (radius - 3));
        ctx.lineTo(Math.cos(ang) * (radius + 3), Math.sin(ang) * (radius + 3));
        ctx.stroke();
      }
      ctx.restore();
    }

    function draw(dt: number) {
      if (!ctx) return;
      t += dt;
      const target = PLASMA_STATES[stateRef.current];
      for (let i = 0; i < 3; i++) cur.tint[i] = lerp(cur.tint[i], target.tint[i], 0.06);
      cur.speed = lerp(cur.speed, target.speed, 0.06);
      cur.swirl = lerp(cur.swirl, target.swirl, 0.06);
      cur.radius = lerp(cur.radius, target.radius, 0.06);
      swirlAcc += cur.speed * dt;

      // speaking: denyut ikut amplitudo TTS nyata bila ada, fallback sinus
      const speakPulse = ampRef.current > 0 ? ampRef.current : 0.3 + Math.abs(Math.sin(t * 6.5)) * 0.7;
      amp = stateRef.current === "speaking" ? lerp(amp, speakPulse, 0.25) : lerp(amp, 0, 0.08);

      const [tr, tg, tb] = cur.tint.map(Math.round);
      ctx.clearRect(0, 0, size, size);
      const breath = reduce ? 1 : 1 + Math.sin(t * 1.3) * 0.025;
      const R = cur.radius * scale * breath * (1 + amp * 0.14);

      const halo = ctx.createRadialGradient(cx, cy, R * 0.5, cx, cy, R * 1.9);
      halo.addColorStop(0, `rgba(${tr},${tg},${tb},0.28)`);
      halo.addColorStop(0.5, `rgba(${tr},${tg},${tb},0.06)`);
      halo.addColorStop(1, `rgba(${tr},${tg},${tb},0)`);
      ctx.fillStyle = halo;
      ctx.fillRect(0, 0, size, size);

      const baseG = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.08);
      baseG.addColorStop(0, `rgba(${tr},${tg},${tb},0.5)`);
      baseG.addColorStop(0.55, `rgba(${Math.round(tr * 0.5)},${Math.round(tg * 0.6)},${Math.round(tb * 0.78)},0.18)`);
      baseG.addColorStop(1, `rgba(${tr},${tg},${tb},0)`);
      ctx.fillStyle = baseG;
      ctx.fillRect(0, 0, size, size);

      ctx.globalCompositeOperation = "lighter";
      for (const bl of blobs) {
        const ang = bl.ang + swirlAcc * cur.swirl * bl.spd;
        const bx = cx + Math.cos(ang + Math.sin(t * 0.7 + bl.phase) * 0.6) * R * bl.orbit;
        const by = cy + Math.sin(ang * 1.1 + Math.cos(t * 0.6 + bl.phase) * 0.6) * R * bl.orbit;
        const col = mixColor(bl.base, cur.tint, 0.45).map(Math.round);
        const rad = R * bl.size;
        const g = ctx.createRadialGradient(bx, by, 0, bx, by, rad);
        g.addColorStop(0, `rgba(${col[0]},${col[1]},${col[2]},0.5)`);
        g.addColorStop(0.5, `rgba(${col[0]},${col[1]},${col[2]},0.12)`);
        g.addColorStop(1, `rgba(${col[0]},${col[1]},${col[2]},0)`);
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, size, size);
      }

      ctx.globalCompositeOperation = "source-over";
      const spec = ctx.createRadialGradient(cx - R * 0.32, cy - R * 0.42, 0, cx - R * 0.32, cy - R * 0.42, R * 0.7);
      spec.addColorStop(0, "rgba(255,255,255,0.3)");
      spec.addColorStop(0.5, "rgba(255,255,255,0.04)");
      spec.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = spec;
      ctx.fillRect(0, 0, size, size);

      const spin = reduce ? 0 : t;
      ring(R * 1.34, 0.4, 2.7, spin * 0.3, 0.28, 7, [tr, tg, tb]);
      ring(R * 1.62, Math.PI + 0.1, Math.PI + 2.2, -spin * 0.22, 0.15, 5, [tr, tg, tb]);
    }

    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      draw(dt);
      raf = requestAnimationFrame(loop);
    };
    if (!paused) {
      raf = requestAnimationFrame(loop);
    } else {
      draw(0); // frame statis supaya orb tetap terlihat saat modal terbuka
    }
    return () => cancelAnimationFrame(raf);
  }, [paused, size]);

  return <canvas ref={canvasRef} className="plasma-orb" aria-hidden="true" />;
}
