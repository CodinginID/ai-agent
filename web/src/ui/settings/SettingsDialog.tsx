import { useIsMobile } from "../../hooks/useIsMobile";
import { BottomSheet } from "../mobile/BottomSheet";
import { SettingsPanel } from "./SettingsPanel";

export interface SettingsDialogProps {
  onClose: () => void;
  onNavigateToPasukan?: () => void;
}

/** Bungkus SettingsPanel sebagai BottomSheet (mobile) / modal tengah (desktop)
 *  — sama seperti AgentEditor. Dipanggil dari SettingsButton. */
export function SettingsDialog({ onClose, onNavigateToPasukan }: SettingsDialogProps): JSX.Element {
  const isMobile = useIsMobile();

  if (isMobile) {
    return (
      <BottomSheet onClose={onClose} title="Pengaturan">
        <SettingsPanel onClose={onClose} onNavigateToPasukan={onNavigateToPasukan} />
      </BottomSheet>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="scroll-thin max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-line bg-panel p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="m-0 mb-3 font-display text-[16px] font-bold text-ink">Pengaturan</h2>
        <SettingsPanel onClose={onClose} onNavigateToPasukan={onNavigateToPasukan} />
      </div>
    </div>
  );
}
