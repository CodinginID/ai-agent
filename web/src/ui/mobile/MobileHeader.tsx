import { useState } from "react";
import { useStore } from "../../state/store";
import { NotifyButton } from "../NotifyButton";
import { MoreMenu } from "./MoreMenu";

/** Header ringkas mobile: logo + judul + status satu baris, lonceng notifikasi
 *  + menu "⋯ Lainnya" (bottom sheet) di kanan. TopBar desktop tak disentuh. */
export function MobileHeader(): JSX.Element {
  const workers = useStore((s) => s.workers);
  const count = useStore((s) => s.agents.length);
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <header className="flex flex-none items-center gap-2.5 border-b border-line bg-surface px-3 py-2">
      <div className="grid h-8 w-8 flex-none place-items-center rounded-lg bg-gradient-to-br from-accent to-[#6b5bd6] text-[16px] shadow-[0_0_0_1px_rgba(56,225,198,.4)_inset]">
        🐙
      </div>

      <div className="min-w-0 flex-1">
        <h1 className="m-0 truncate font-display text-[14px] font-bold leading-tight text-ink">
          Ruang Octopus
        </h1>
        <div className="flex items-center gap-1.5 truncate font-mono text-[10.5px] text-ink-soft">
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

      <NotifyButton />

      <button
        type="button"
        onClick={() => setMoreOpen(true)}
        title="Lainnya"
        aria-label="Menu lainnya"
        className="grid h-9 w-9 flex-none place-items-center rounded-lg border border-line text-[18px] leading-none text-ink-soft"
      >
        ⋯
      </button>

      {moreOpen && <MoreMenu onClose={() => setMoreOpen(false)} />}
    </header>
  );
}
