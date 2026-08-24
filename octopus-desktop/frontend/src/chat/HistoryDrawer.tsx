import type { AssistantMessage, Message } from "./types";
import { useI18n } from "../i18n/useI18n";

export interface HistoryDrawerProps {
  open: boolean;
  onClose: () => void;
  messages: Message[];
}

function assistantSnippet(m: AssistantMessage): string {
  if (m.finalText) return m.finalText;
  const text = m.parts.find((p) => p.kind === "text");
  return text && text.kind === "text" ? text.text : "…";
}

// Drawer riwayat: giliran percakapan lampau (read-only). UI utama ephemeral,
// riwayat tetap tersimpan dan diakses dari sini.
export function HistoryDrawer({ open, onClose, messages }: HistoryDrawerProps) {
  const { t } = useI18n();
  return (
    <div className={`history-drawer ${open ? "open" : ""}`} aria-hidden={!open}>
      <header className="history-head">
        <span>{t("history_title")}</span>
        <button onClick={onClose} aria-label={t("history_close")}>
          ✕
        </button>
      </header>
      <div className="history-list">
        {messages.length === 0 && <p className="history-empty">{t("history_empty")}</p>}
        {messages.map((m) => (
          <div key={m.msgId} className={`history-item ${m.role}`}>
            <span className="history-role">{m.role === "user" ? t("history_you") : t("history_bot")}</span>
            <p>{m.role === "user" ? m.text : assistantSnippet(m)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
