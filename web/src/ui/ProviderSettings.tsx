import { useState } from "react";
import { useIsMobile } from "../hooks/useIsMobile";
import {
  getApiKey,
  getProvider,
  isRealMode,
  setApiKey,
  setProvider,
} from "../net/api";
import { BottomSheet } from "./mobile/BottomSheet";

export interface ProviderEditorProps {
  onClose: () => void;
}

/** Editor provider BYOK (dulu isi modal ProviderButton) — kini dipanggil dari
 *  SettingsPanel (bagian "Otak"), sheet di mobile / modal di desktop seperti
 *  AgentEditor. Tanpa tombol trigger sendiri; pemanggil yang mengelola open state. */
export function ProviderEditor({ onClose }: ProviderEditorProps): JSX.Element {
  const isMobile = useIsMobile();
  const [provider, setProviderState] = useState(getProvider());
  const [key, setKeyState] = useState(getApiKey());

  const save = (): void => {
    setProvider(provider);
    setApiKey(provider === "mock" ? "" : key.trim());
    onClose();
  };

  const content = (
    <div className="flex flex-col gap-3">
      <p className="m-0 text-[12.5px] leading-relaxed text-ink-soft">
        Pilih provider &amp; tempel API key kamu (BYOK). Tanpa key = mode mock.
        Key disimpan di browser ini &amp; dikirim per-perintah — tidak
        dipersist di server.
      </p>

      <div>
        <label className="block font-mono text-[11px] uppercase tracking-wide text-ink-faint">
          Provider
        </label>
        <select
          value={provider}
          onChange={(e) => setProviderState(e.target.value)}
          className="mt-1 w-full rounded-lg border border-line bg-surface-2 px-3 py-2.5 text-[14px] text-ink"
        >
          <option value="mock">mock (demo, tanpa key)</option>
          <option value="anthropic">anthropic (Claude)</option>
          <option value="glm">glm (Zhipu)</option>
        </select>
      </div>

      {provider !== "mock" && (
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-ink-faint">
            API Key
          </label>
          <input
            type="password"
            value={key}
            onChange={(e) => setKeyState(e.target.value)}
            placeholder={provider === "anthropic" ? "sk-ant-..." : "glm key..."}
            className="mt-1 w-full rounded-lg border border-line bg-surface-2 px-3 py-2.5 font-mono text-[13px] text-ink"
          />
        </div>
      )}

      <div className="mt-1 flex gap-2">
        <button
          type="button"
          onClick={save}
          className="min-h-[44px] flex-1 rounded-lg bg-accent text-[13px] font-semibold text-accent-ink"
        >
          Simpan
        </button>
        <button
          type="button"
          onClick={onClose}
          className="min-h-[44px] flex-1 rounded-lg border border-line text-[13px] font-semibold text-ink-soft"
        >
          Batal
        </button>
      </div>
    </div>
  );

  if (isMobile) {
    return (
      <BottomSheet onClose={onClose} title="Otak (LLM provider)">
        {content}
      </BottomSheet>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-line bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="m-0 mb-3 font-display text-[16px] font-bold text-ink">
          Otak (LLM provider)
        </h2>
        {content}
      </div>
    </div>
  );
}

/** Ringkasan provider aktif untuk baris "Otak" di SettingsPanel. */
export function providerSummary(): string {
  return isRealMode() ? `${getProvider()} · key tersimpan` : "mock (tanpa key)";
}
