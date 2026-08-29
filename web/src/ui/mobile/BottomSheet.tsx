import type { ReactNode } from "react";

export interface BottomSheetProps {
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
}

/** Sheet generik dari bawah layar (dipakai MoreMenu, ApprovalSheet, AgentEditor
 *  mobile) — backdrop gelap + drag handle + judul opsional, tutup lewat
 *  backdrop atau tombol "Tutup" pemanggil sendiri di dalam `children`. */
export function BottomSheet({ onClose, title, children }: BottomSheetProps): JSX.Element {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="sheet-in max-h-[85dvh] w-full max-w-lg overflow-hidden rounded-t-2xl border-t border-line bg-panel shadow-xl"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-center pb-1 pt-2.5">
          <span className="h-1 w-10 rounded-full bg-line" />
        </div>
        {title && (
          <div className="px-4 pb-1 pt-1 font-display text-[16px] font-bold text-ink">
            {title}
          </div>
        )}
        <div className="scroll-thin max-h-[75dvh] overflow-y-auto px-4 pb-4 pt-2">
          {children}
        </div>
      </div>
    </div>
  );
}
