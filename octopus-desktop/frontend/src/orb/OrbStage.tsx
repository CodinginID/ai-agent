import type { ReactNode } from "react";
import { PlasmaOrb } from "./PlasmaOrb";
import { PLASMA_STATES } from "./plasma";
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

// Panggung orb: orb plasma besar di tengah (klik = mulai listen / barge-in),
// hint saat hover, label state mono, lalu lapisan respons ephemeral.
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
        <PlasmaOrb state={state} amplitude={amplitude} paused={paused} />
        <span className="orb-hint">{t(HINT[state])}</span>
      </div>
      <div className="state-label">{t(PLASMA_STATES[state].labelKey)}</div>
      {children}
    </div>
  );
}
