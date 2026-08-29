import { useStore } from "../../state/store";
import { ApprovalQueue } from "../ApprovalQueue";
import { BottomSheet } from "./BottomSheet";

export interface ApprovalSheetProps {
  onClose: () => void;
}

/** Sheet yang muncul otomatis saat ada approval.request baru (lihat
 *  MobileShell) — isinya ApprovalQueue yang sama dengan tab Persetujuan,
 *  cuma dibungkus judul + count pill + tombol Tutup. */
export function ApprovalSheet({ onClose }: ApprovalSheetProps): JSX.Element {
  const count = useStore((s) => s.serverApprovals.length + s.approvals.length);

  return (
    <BottomSheet
      onClose={onClose}
      title={
        <div className="flex items-center gap-2">
          <span>Perlu persetujuan</span>
          <span className="grid h-5 min-w-[20px] place-items-center rounded-full bg-st-approval px-1.5 text-[11px] font-bold text-[#201400]">
            {count}
          </span>
        </div>
      }
    >
      <ApprovalQueue />
      <button
        type="button"
        onClick={onClose}
        className="mt-3 min-h-[48px] w-full rounded-lg border border-line text-[13px] font-semibold text-ink"
      >
        Tutup
      </button>
    </BottomSheet>
  );
}
