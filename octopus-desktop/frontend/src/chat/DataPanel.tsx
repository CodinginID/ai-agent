import type { Part } from "./types";
import { PartCard } from "./PartCard";
import { useI18n } from "../i18n/useI18n";

export interface DataPanelProps {
  parts: Part[];
  onClose?: () => void;
  onApprove?: (planId: string) => void;
  onReject?: (planId: string) => void;
  onRetry?: () => void;
}

// Part kaya yang layak tampil sebagai baris accordion (teks & status
// ditangani ResponseLayer / indikator orb, bukan di sini).
function isRichPart(p: Part): boolean {
  return p.kind === "action" || p.kind === "approval" || p.kind === "error";
}

function partLabel(p: Part, t: (key: string, vars?: Record<string, string>) => string): string {
  switch (p.kind) {
    case "action":
      return p.running ? `${p.action}…` : p.action;
    case "approval":
      return t("data_panel_approval", { summary: p.summary.slice(0, 48) });
    case "error":
      return t("data_panel_error");
    default:
      return "";
  }
}

function defaultOpen(p: Part): boolean {
  return p.kind === "approval" || p.kind === "error";
}

// Panel accordion melayang untuk hasil kaya giliran berjalan.
export function DataPanel({ parts, onClose, onApprove, onReject, onRetry }: DataPanelProps) {
  const { t } = useI18n();
  const rich = parts.filter(isRichPart);
  if (rich.length === 0) return null;
  return (
    <aside className="data-panel" aria-label={t("data_panel_title")}>
      <header className="data-panel-head">
        <span>{t("data_panel_count", { count: String(rich.length) })}</span>
        <button className="data-panel-close" onClick={onClose} aria-label={t("data_panel_close")}>
          ✕
        </button>
      </header>
      <div className="data-accordion">
        {rich.map((p, i) => (
          <details key={i} className="data-row" open={defaultOpen(p)}>
            <summary>{partLabel(p, t)}</summary>
            <div className="data-row-body">
              <PartCard part={p} onApprove={onApprove} onReject={onReject} onRetry={onRetry} />
            </div>
          </details>
        ))}
      </div>
    </aside>
  );
}
