import { useStore } from "../../state/store";
import { ProviderButton } from "../ProviderSettings";
import { UpdateButton } from "../UpdateButton";
import { BottomSheet } from "./BottomSheet";

export interface MoreMenuProps {
  onClose: () => void;
}

/** Menu "⋯ Lainnya" mobile — isi TopBar desktop yang tak muat di header
 *  ringkas: provider BYOK, versi/update, ganti tema. */
export function MoreMenu({ onClose }: MoreMenuProps): JSX.Element {
  const theme = useStore((s) => s.theme);
  const toggleTheme = useStore((s) => s.toggleTheme);

  return (
    <BottomSheet onClose={onClose} title="Lainnya">
      <div className="flex flex-col gap-2">
        <ProviderButton />
        <UpdateButton />
        <button
          type="button"
          onClick={toggleTheme}
          className="flex min-h-[44px] items-center justify-between rounded-lg border border-line px-3 py-2 text-[13px] font-semibold text-ink"
        >
          Tema
          <span>{theme === "dark" ? "☀ Terang" : "◐ Gelap"}</span>
        </button>
      </div>
    </BottomSheet>
  );
}
