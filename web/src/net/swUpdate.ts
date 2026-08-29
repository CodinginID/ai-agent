// Registrasi service worker (satu-satunya titik) + wiring status pembaruan
// ke zustand store (`useStore().update`) supaya TopBar/MobileHeader (badge
// titik di ikon gerigi) dan SettingsPanel (bagian Tentang) bisa membaca state
// yang sama. Dipanggil sekali dari main.tsx.

import { registerSW } from "virtual:pwa-register";
import { setSwHandle, useStore } from "../state/store";
import { fetchLatestVersion } from "./version";

// Cek versi baru berkala saat tab hidup (SW hanya auto-cek saat navigasi).
const CHECK_INTERVAL_MS = 60_000;

let initialized = false;

/** Registrasi SW + mulai polling pembaruan berkala. Aman dipanggil berkali-kali
 *  (mis. React StrictMode double-invoke efek) — cuma jalan sekali. */
export function initSwUpdate(): void {
  if (initialized) return;
  if (typeof window === "undefined") return;
  initialized = true;

  // "prompt" (vite.config.ts): SW baru menunggu sampai applyUpdate() dipanggil
  // → updateServiceWorker(true) kirim SKIP_WAITING lalu reload otomatis.
  const updateServiceWorker = registerSW({
    immediate: true,
    onNeedRefresh() {
      useStore.setState((s) => ({ update: { ...s.update, available: true } }));
      // Ambil catatan rilis versi baru dari server begitu SW baru terdeteksi.
      void fetchLatestVersion().then((info) => {
        if (info) {
          useStore.setState((s) => ({ update: { ...s.update, latest: info } }));
        }
      });
    },
    onRegisteredSW(_swScriptUrl, reg) {
      setSwHandle({ reg, updateServiceWorker });
      if (!reg) return;

      const check = (): void => {
        if (document.visibilityState !== "visible" || !navigator.onLine) return;
        void reg.update().catch(() => {});
      };
      window.setInterval(check, CHECK_INTERVAL_MS);
      document.addEventListener("visibilitychange", check);
      window.addEventListener("online", check);
    },
  });

  // registerSW() sudah mengembalikan updateServiceWorker secara sinkron —
  // simpan handle awal (reg belum ada) supaya applyUpdate() tak pernah no-op
  // kalau dipanggil sebelum onRegisteredSW sempat terpanggil.
  setSwHandle({ reg: undefined, updateServiceWorker });
}
