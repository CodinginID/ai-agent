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
  const ua = window.navigator.userAgent;
  const isIos = /iPad|iPhone|iPod/.test(ua);
  const isStandalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    (window.navigator as unknown as { standalone?: boolean }).standalone === true;
  return isIos && !isStandalone;
}

const LABEL: Record<PushState, string> = {
  enabled: "🔔 aktif",
  disabled: "🔕 nonaktif",
  denied: "🚫 diblokir",
  unsupported: "",
};

/** Tombol lonceng di TopBar — aktifkan/nonaktifkan Web Push notification. */
export function NotifyButton(): JSX.Element | null {
  const [state, setState] = useState<PushState>("unsupported");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!isPushSupported()) {
      setState("unsupported");
      return;
    }
    void getPushState().then(setState);
  }, []);

  if (!isPushSupported()) return null;

  const iosBlocked = isIosNonStandalone();

  const toggle = async (): Promise<void> => {
    if (busy) return;
    if (iosBlocked) return;
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

  const title = iosBlocked
    ? "Install ke Home Screen dulu (iOS) untuk notifikasi"
    : state === "denied"
      ? "Notifikasi diblokir di pengaturan browser"
      : "Notifikasi push (approval & tugas selesai)";

  return (
    <button
      type="button"
      onClick={() => void toggle()}
      disabled={busy || state === "denied"}
      title={title}
      aria-label="Notifikasi push"
      className={`rounded-lg border px-2.5 py-2 font-mono text-[12px] font-semibold transition ${
        state === "enabled"
          ? "border-accent text-accent"
          : "border-line text-ink-soft hover:border-accent"
      }`}
    >
      {LABEL[state]}
    </button>
  );
}
