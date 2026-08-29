import { useState } from "react";
import { useStore } from "../../state/store";
import { SettingsDialog } from "./SettingsDialog";

export interface SettingsButtonProps {
  /** Mobile only: diteruskan ke SettingsPanel supaya "Kelola pasukan"
   *  memindahkan tab alih-alih membuka AgentEditor sebagai modal. */
  onNavigateToPasukan?: () => void;
}

/** Satu-satunya titik masuk ke Pengaturan — gerigi 44px, titik aksen kalau ada
 *  pembaruan menunggu. Menggantikan ProviderButton/NotifyButton/UpdateButton
 *  (TopBar) dan menu "⋯ Lainnya" (mobile). */
export function SettingsButton({ onNavigateToPasukan }: SettingsButtonProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const updateAvailable = useStore((s) => s.update.available);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Pengaturan"
        aria-label="Pengaturan"
        className="relative grid h-10 w-10 flex-none place-items-center rounded-lg border border-line text-ink-soft transition hover:border-accent hover:text-ink"
      >
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
          <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
        {updateAvailable && (
          <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-accent shadow-[0_0_6px_var(--accent)]" />
        )}
      </button>

      {open && (
        <SettingsDialog
          onClose={() => setOpen(false)}
          onNavigateToPasukan={onNavigateToPasukan}
        />
      )}
    </>
  );
}
