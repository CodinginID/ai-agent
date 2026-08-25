import { useState } from "react";
import {
  getApiKey,
  getProvider,
  isRealMode,
  setApiKey,
  setProvider,
} from "../net/api";

/** Tombol + modal untuk mengaktifkan mode IT-Manager asli (BYOK). */
export function ProviderButton(): JSX.Element {
  const [open, setOpen] = useState(false);
  const [provider, setProviderState] = useState(getProvider());
  const [key, setKeyState] = useState(getApiKey());
  const [active, setActive] = useState(isRealMode());

  const save = (): void => {
    setProvider(provider);
    setApiKey(provider === "mock" ? "" : key.trim());
    setActive(provider !== "mock" && key.trim().length > 0);
    setOpen(false);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Provider & API key (aktifkan IT-Manager)"
        className={`rounded-lg border px-2.5 py-2 font-mono text-[12px] font-semibold transition ${
          active
            ? "border-accent text-accent"
            : "border-line text-ink-soft hover:border-accent"
        }`}
      >
        {active ? `● ${getProvider()}` : "◌ mock"}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-2xl border border-line bg-surface p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="m-0 font-display text-[16px] font-bold text-ink">
              Aktifkan IT-Manager
            </h2>
            <p className="mb-4 mt-1 text-[12.5px] leading-relaxed text-ink-soft">
              Pilih provider &amp; tempel API key kamu (BYOK). Tanpa key = mode
              mock. Key disimpan di browser ini &amp; dikirim per-perintah — tidak
              dipersist di server.
            </p>

            <label className="block font-mono text-[11px] uppercase tracking-wide text-ink-faint">
              Provider
            </label>
            <select
              value={provider}
              onChange={(e) => setProviderState(e.target.value)}
              className="mb-3 mt-1 w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-[14px] text-ink"
            >
              <option value="mock">mock (demo, tanpa key)</option>
              <option value="anthropic">anthropic (Claude)</option>
              <option value="glm">glm (Zhipu)</option>
            </select>

            {provider !== "mock" && (
              <>
                <label className="block font-mono text-[11px] uppercase tracking-wide text-ink-faint">
                  API Key
                </label>
                <input
                  type="password"
                  value={key}
                  onChange={(e) => setKeyState(e.target.value)}
                  placeholder={provider === "anthropic" ? "sk-ant-..." : "glm key..."}
                  className="mb-3 mt-1 w-full rounded-lg border border-line bg-surface-2 px-3 py-2 font-mono text-[13px] text-ink"
                />
              </>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg border border-line px-3 py-2 text-[13px] text-ink-soft"
              >
                Batal
              </button>
              <button
                type="button"
                onClick={save}
                className="rounded-lg bg-accent px-3 py-2 text-[13px] font-semibold text-[#062019]"
              >
                Simpan
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
