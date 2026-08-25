import { ROLE } from "../room/engine/scene";
import { useStore } from "../state/store";

export function ApprovalQueue(): JSX.Element {
  const approvals = useStore((s) => s.approvals);
  const serverApprovals = useStore((s) => s.serverApprovals);
  const agents = useStore((s) => s.agents);
  const approve = useStore((s) => s.approve);
  const reject = useStore((s) => s.reject);
  const approveServer = useStore((s) => s.approveServer);
  const rejectServer = useStore((s) => s.rejectServer);

  if (!approvals.length && !serverApprovals.length) {
    return (
      <p className="text-[12.5px] text-ink-faint">
        Tidak ada permintaan. Aksi berisiko akan muncul di sini.
      </p>
    );
  }

  const cardStyle = {
    borderColor: "color-mix(in oklab, var(--st-approval) 45%, var(--line))",
    background: "color-mix(in oklab, var(--st-approval) 9%, var(--panel))",
  };
  const yesCls =
    "flex-1 rounded-lg border border-transparent bg-st-approval py-1.5 text-center text-[12.5px] font-semibold text-[#201400]";
  const noCls =
    "flex-1 rounded-lg border border-line bg-transparent py-1.5 text-center text-[12.5px] font-semibold text-ink transition hover:border-st-error";

  return (
    <div className="flex flex-col gap-2.5">
      {/* Approval backend nyata (dari /room/stream) */}
      {serverApprovals.map((r) => (
        <div key={r.planId} className="rounded-[11px] border p-3" style={cardStyle}>
          <div className="text-[13px] font-semibold text-ink">🛰️ Backend</div>
          <div className="my-1 mb-2.5 whitespace-pre-line text-[12.5px] text-ink-soft">
            {r.desc}
          </div>
          <div className="flex gap-2">
            <button onClick={() => approveServer(r.planId)} className={yesCls}>
              Setujui
            </button>
            <button onClick={() => rejectServer(r.planId)} className={noCls}>
              Tolak
            </button>
          </div>
        </div>
      ))}

      {/* Approval mock (ambience scheduler) */}
      {approvals.map((r) => {
        const agent = agents.find((a) => a.id === r.agentId);
        const icon = agent ? ROLE[agent.role].icon : "⚙";
        return (
          <div key={r.id} className="rounded-[11px] border p-3" style={cardStyle}>
            <div className="text-[13px] font-semibold text-ink">
              {icon} {agent?.name ?? "Agen"}
            </div>
            <div className="my-1 mb-2.5 text-[12.5px] text-ink-soft">
              ingin menjalankan: <b className="text-ink">{r.task.desc}</b>
            </div>
            <div className="flex gap-2">
              <button onClick={() => approve(r.id)} className={yesCls}>
                Setujui
              </button>
              <button onClick={() => reject(r.id)} className={noCls}>
                Tolak
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
