import type { ReactNode } from "react";
import { AiOrb } from "./AiOrb";
import type { OrbState } from "./orbState";

export interface OrbStageProps {
  state: OrbState;
  amplitude?: number;
  paused?: boolean;
  onActivate?: () => void;
  children?: ReactNode; // ResponseLayer, dsb.
}

const HINT: Record<OrbState, string> = {
  idle: "Klik untuk bicara",
  listening: "Mendengarkan…",
  thinking: "Berpikir…",
  speaking: "Klik untuk menyela",
};

// Panggung orb: orb besar di tengah (klik = mulai listen / barge-in) + cincin
// HUD berputar + lapisan respons ephemeral.
export function OrbStage({ state, amplitude = 0, paused = false, onActivate, children }: OrbStageProps) {
  return (
    <div className="orb-stage">
      <div
        className={`orb-core state-${state}`}
        role="button"
        tabIndex={0}
        aria-label={HINT[state]}
        onClick={onActivate}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onActivate?.();
          }
        }}
      >
        <div className="orb-hud-ring" aria-hidden="true" />
        <AiOrb state={state} amplitude={amplitude} paused={paused} />
      </div>
      <span className="orb-hint">{HINT[state]}</span>
      {children}
    </div>
  );
}
