import { useState } from "react";
import { useStore } from "../../state/store";
import { NotifyButton } from "../NotifyButton";
import { MoreMenu } from "./MoreMenu";

/** Header ringkas mobile: logo + judul + status satu baris, lonceng notifikasi
 *  + menu "⋯ Lainnya" (bottom sheet) di kanan. TopBar desktop tak disentuh. */
export interface MobileHeaderProps {
  /** Mode layar pendek: tampilkan tombol tulis perintah (command bar disembunyikan). */
  onCompose?: () => void;
}

export function MobileHeader({ onCompose }: MobileHeaderProps = {}): JSX.Element {
  const workers = useStore((s) => s.workers);
  const count = useStore((s) => s.agents.length);
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <header
      className="flex flex-none items-center gap-2.5 border-b border-line bg-surface px-3 pb-2"
      style={{ paddingTop: "calc(8px + env(safe-area-inset-top))" }}
    >
      <div className="grid h-8 w-8 flex-none place-items-center rounded-lg bg-gradient-to-br from-accent to-[#6b5bd6] text-[16px] shadow-[0_0_0_1px_rgba(56,225,198,.4)_inset]">
        🐙
      </div>

      <div className="min-w-0 flex-1">
        <h1 className="m-0 truncate font-display text-[16px] font-bold leading-tight text-ink">
          Ruang Octopus
        </h1>
        <div className="flex items-center gap-1.5 truncate font-mono text-[11.5px] text-ink-soft">
          <span
            className={
              workers > 0
                ? "h-[6px] w-[6px] flex-none rounded-full bg-[#3ddc84] shadow-[0_0_6px_#3ddc84]"
                : "h-[6px] w-[6px] flex-none rounded-full bg-ink-faint"
            }
          />
          {workers} pasukan online · {count} agen
        </div>
      </div>

      {onCompose && (
        <button
          type="button"
          onClick={onCompose}
          aria-label="Tulis perintah"
          className="grid h-10 w-10 flex-none place-items-center rounded-lg bg-accent text-accent-ink"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17z" />
            <path d="m13.5 6.5 3 3" />
          </svg>
        </button>
      )}

      <NotifyButton />

      <button
        type="button"
        onClick={() => setMoreOpen(true)}
        title="Lainnya"
        aria-label="Menu lainnya"
        className="grid h-10 w-10 flex-none place-items-center rounded-lg border border-line text-[18px] leading-none text-ink-soft"
      >
        ⋯
      </button>

      {moreOpen && <MoreMenu onClose={() => setMoreOpen(false)} />}
    </header>
  );
}
