import { memo } from "react";
import type { JSX } from "react";
import type { AvatarWorkerState } from "./types";
import { useI18n } from "../i18n/useI18n";

interface AvatarProps {
  workerId: string;
  workerName: string;
  workerType: string;
  workerColor: string;
  state: AvatarWorkerState;
  task?: string;
  amplitude?: number;
}

// SVG path definitions per worker type
const SVG_SHAPES: Record<string, React.ReactElement> = {
  gear: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="avatar-svg">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  ),
  "magnifying-glass": (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="avatar-svg">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  ),
  blueprint: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="avatar-svg">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18M9 21V9" />
    </svg>
  ),
  server: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="avatar-svg">
      <rect x="2" y="2" width="20" height="8" rx="2" />
      <rect x="2" y="14" width="20" height="8" rx="2" />
      <circle cx="6" cy="6" r="1" fill="currentColor" />
      <circle cx="6" cy="18" r="1" fill="currentColor" />
    </svg>
  ),
  container: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="avatar-svg">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
      <line x1="12" y1="22.08" x2="12" y2="12" />
    </svg>
  ),
};

const DEFAULT_SVG = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="avatar-svg">
    <circle cx="12" cy="12" r="10" />
    <path d="M12 16v-4M12 8h.01" />
  </svg>
);

function resolveSvg(type: string): React.ReactElement {
  return SVG_SHAPES[type] || DEFAULT_SVG;
}

export const Avatar = memo(function Avatar({
  workerId,
  workerName,
  workerType,
  workerColor,
  state,
  task,
  amplitude = 0,
}: AvatarProps) {
  const { t } = useI18n();
  const svg = resolveSvg(workerType);
  const isSpeaking = amplitude > 0.05;
  const scale = 1 + (amplitude * 0.15);

  return (
    <div
      className={`avatar ${state === "working" ? "avatar--working" : state === "error" ? "avatar--error" : ""} ${isSpeaking ? "avatar--speaking" : ""}`}
      data-worker-id={workerId}
      role="img"
      aria-label={`${workerName} ${state === "working" ? t("avatar_aria_working") : state === "error" ? t("avatar_aria_error") : t("avatar_aria_idle")}`}
      title={t("avatar_title", { workerName, task: task ?? workerName })}
    >
      <div
        className="avatar-circle"
        style={{
          backgroundColor: `${workerColor}18`,
          borderColor: workerColor,
          transform: `scale(${scale})`,
          transition: "transform 0.08s ease-out",
        }}
      >
        <span
          className="avatar-icon"
          style={{ color: workerColor }}
        >
          {svg}
        </span>
        {state === "working" && <span className="avatar-pulse-ring" />}
        {isSpeaking && <span className="avatar-speak-ring" />}
      </div>
      <div className="avatar-label">
        <div className="avatar-name">{workerName}</div>
        {task && <div className="avatar-task">{task}</div>}
      </div>
    </div>
  );
});
