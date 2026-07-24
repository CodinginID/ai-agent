import type { ReactNode } from "react";
import { AiOrb } from "./AiOrb";
import type { OrbState } from "./orbState";
import { useI18n } from "../i18n/useI18n";

export interface OrbStageProps {
  state: OrbState;
  amplitude?: number;
  paused?: boolean;
  onActivate?: () => void;
  children?: ReactNode; // ResponseLayer, dsb.
}

const HINT: Record<OrbState, string> = {
  idle: "orb_hint_idle",
  listening: "orb_hint_listening",
  thinking: "orb_hint_thinking",
  speaking: "orb_hint_speaking",
};

// Panggung orb: orb besar di tengah (klik = mulai listen / barge-in) + cincin
// HUD berputar + lapisan respons ephemeral.
export function OrbStage({ state, amplitude = 0, paused = false, onActivate, children }: OrbStageProps) {
  const { t } = useI18n();
  return (
    <div className="orb-stage">
      <div
        className={`orb-core state-${state}`}
        role="button"
        tabIndex={0}
        aria-label={t(HINT[state])}
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
      <span className="orb-hint">{t(HINT[state])}</span>
      {children}
    </div>
  );
}
