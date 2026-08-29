import { useEffect, useState } from "react";
import {
  disablePush,
  enablePush,
  getPushState,
  isPushSupported,
  syncTokenToSw,
  type PushState,
} from "../net/push";

/** iOS Safari cuma dukung Web Push kalau app sudah "Add to Home Screen". */
function isIosNonStandalone(): boolean {
  if (typeof window === "undefined") return false;
  const ua = window.navigator.userAgent;
  const isIos = /iPad|iPhone|iPod/.test(ua);
  const isStandalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    (window.navigator as unknown as { standalone?: boolean }).standalone === true;
  return isIos && !isStandalone;
}

export interface PushToggle {
  /** false = browser ini tidak dukung Web Push sama sekali (sembunyikan UI). */
  supported: boolean;
  state: PushState;
  busy: boolean;
  /** true = iOS belum di-"Add to Home Screen" — notifikasi tak bisa diaktifkan. */
  iosBlocked: boolean;
  toggle: () => Promise<void>;
}

/** Logic tombol notifikasi push (dulu NotifyButton) — dipakai SettingsPanel
 *  bagian Notifikasi. Cuma state + aksi; tak render apa pun. */
export function usePushToggle(): PushToggle {
  const supported = isPushSupported();
  const [state, setState] = useState<PushState>(supported ? "disabled" : "unsupported");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!supported) {
      setState("unsupported");
      return;
    }
    void getPushState().then(setState);
  }, [supported]);

  const iosBlocked = isIosNonStandalone();

  const toggle = async (): Promise<void> => {
    if (busy || !supported || iosBlocked) return;
    setBusy(true);
    try {
      if (state === "enabled") {
        const ok = await disablePush();
        if (ok) setState("disabled");
      } else {
        const ok = await enablePush();
        if (ok) {
          await syncTokenToSw();
          setState("enabled");
        } else {
          setState(await getPushState());
        }
      }
    } finally {
      setBusy(false);
    }
  };

  return { supported, state, busy, iosBlocked, toggle };
}
