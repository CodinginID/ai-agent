import type { ReactNode } from "react";

const CARD_STYLE = {
  borderColor: "color-mix(in oklab, var(--st-approval) 45%, var(--line))",
  background: "color-mix(in oklab, var(--st-approval) 9%, var(--panel))",
};

export interface ApprovalCardProps {
  title: ReactNode;
  desc: ReactNode;
  onApprove: () => void;
  onReject: () => void;
  /** Tombol minimal 48px — dipakai di mobile (ApprovalSheet / tab Persetujuan). */
  tall?: boolean;
}

/** Kartu persetujuan dipakai bersama oleh ApprovalQueue (desktop & mobile,
 *  lewat useIsMobile) dan ApprovalSheet — satu tempat untuk styling & markup. */
export function ApprovalCard({ title, desc, onApprove, onReject, tall }: ApprovalCardProps): JSX.Element {
  const btnH = tall ? "min-h-[48px]" : "py-1.5";
  const txt = tall ? "text-[15px]" : "text-[12.5px]";
  const yesCls = `flex-1 rounded-xl border border-transparent bg-st-approval text-center font-semibold text-[#201400] ${txt} ${btnH}`;
  const noCls = `flex-1 rounded-xl border border-line bg-transparent text-center font-semibold text-ink transition hover:border-st-error ${txt} ${btnH}`;

  return (
    <div className="rounded-[11px] border p-3" style={CARD_STYLE}>
      <div className={`font-semibold text-ink ${tall ? "text-[15px]" : "text-[13px]"}`}>{title}</div>
      <div className={`my-1 mb-2.5 whitespace-pre-line text-ink-soft ${tall ? "text-[14px]" : "text-[12.5px]"}`}>{desc}</div>
      <div className="flex gap-2">
        <button type="button" onClick={onApprove} className={yesCls}>
          Setujui
        </button>
        <button type="button" onClick={onReject} className={noCls}>
          Tolak
        </button>
      </div>
    </div>
  );
}
