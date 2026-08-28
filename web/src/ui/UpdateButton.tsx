import { useCallback, useEffect, useState } from "react";
import { useRegisterSW } from "virtual:pwa-register/react";
import { CHANGELOG } from "../changelog";
import { CURRENT_VERSION, fetchLatestVersion, type VersionInfo } from "../net/version";

// Cek versi baru berkala saat tab hidup (SW hanya auto-cek saat navigasi).
const CHECK_INTERVAL_MS = 60_000;

/** Tombol versi di TopBar: "v0.2.0" biasa; saat SW baru menunggu → "⬆ Update
 *  v0.3.0" (accent). Klik → panel daftar perubahan + tombol "Perbarui sekarang". */
export function UpdateButton(): JSX.Element {
  const [open, setOpen] = useState(false);
  const [latest, setLatest] = useState<VersionInfo | null>(null);

  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, reg) {
      if (!reg) return;
      const check = (): void => {
        if (document.visibilityState !== "visible" || !navigator.onLine) return;
        void reg.update().catch(() => {});
      };
      const timer = window.setInterval(check, CHECK_INTERVAL_MS);
      document.addEventListener("visibilitychange", check);
      // Tab jarang di-unmount; cleanup defensif bila pernah.
      window.addEventListener("beforeunload", () => window.clearInterval(timer), { once: true });
    },
  });

  // SW baru terdeteksi → ambil catatan rilis versi baru dari server.
  useEffect(() => {
    if (!needRefresh) return;
    void fetchLatestVersion().then(setLatest);
  }, [needRefresh]);

  const applyUpdate = useCallback((): void => {
    setOpen(false);
    void updateServiceWorker(true); // SKIP_WAITING → reload otomatis
  }, [updateServiceWorker]);

  const newVersion = latest && latest.version !== CURRENT_VERSION ? latest.version : null;
  const notes: string[] = needRefresh
    ? latest?.notes ?? []
    : CHANGELOG.find((r) => r.version === CURRENT_VERSION)?.notes ?? [];

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={needRefresh ? "Versi baru tersedia — klik untuk lihat perubahan" : "Versi aplikasi & riwayat perubahan"}
        className={`rounded-lg border px-2.5 py-2 font-mono text-[12px] font-semibold transition ${
          needRefresh
            ? "animate-pulse border-accent bg-accent/10 text-accent"
            : "border-line text-ink-soft hover:border-accent"
        }`}
      >
        {needRefresh ? `⬆ Update${newVersion ? ` v${newVersion}` : ""}` : `v${CURRENT_VERSION}`}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-line bg-panel p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="m-0 font-display text-[15px] font-bold text-ink">
              {needRefresh
                ? `Pembaruan tersedia${newVersion ? ` — v${newVersion}` : ""}`
                : `Ruang Octopus v${CURRENT_VERSION}`}
            </h3>
            <p className="mb-3 mt-1 text-[12px] text-ink-faint">
              {needRefresh
                ? `Versi saat ini v${CURRENT_VERSION}. Perubahan di versi baru:`
                : "Yang ada di versi ini:"}
            </p>

            {notes.length ? (
              <ul className="m-0 mb-4 list-disc space-y-1.5 pl-5 text-[13px] text-ink-soft">
                {notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            ) : (
              <p className="mb-4 text-[13px] text-ink-soft">
                {needRefresh
                  ? "Rincian perubahan belum bisa diambil (offline?). Pembaruan tetap bisa dipasang."
                  : "Belum ada catatan rilis."}
              </p>
            )}

            <div className="flex gap-2">
              {needRefresh ? (
                <>
                  <button
                    type="button"
                    onClick={applyUpdate}
                    className="flex-1 rounded-lg bg-accent py-2 text-[13px] font-semibold text-[#08221d]"
                  >
                    Perbarui sekarang
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      setNeedRefresh(false); // sembunyikan sampai cek berikutnya
                    }}
                    className="flex-1 rounded-lg border border-line py-2 text-[13px] font-semibold text-ink"
                  >
                    Nanti
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex-1 rounded-lg border border-line py-2 text-[13px] font-semibold text-ink"
                >
                  Tutup
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
