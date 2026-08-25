import { useStore } from "../state/store";
import { ROLE } from "../room/engine/scene";

export function ApprovalQueue(): JSX.Element {
  const approvals = useStore((s) => s.approvals);
  const agents = useStore((s) => s.agents);
  const approve = useStore((s) => s.approve);
  const reject = useStore((s) => s.reject);

  if (!approvals.length) {
    return (
      <p className="text-[12.5px] text-ink-faint">
        Tidak ada permintaan. Aksi berisiko akan muncul di sini.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2.5">
      {approvals.map((r) => {
        const agent = agents.find((a) => a.id === r.agentId);
        const icon = agent ? ROLE[agent.role].icon : "⚙";
        return (
          <div
            key={r.id}
            className="rounded-[11px] border p-3"
            style={{
              borderColor: "color-mix(in oklab, var(--st-approval) 45%, var(--line))",
              background: "color-mix(in oklab, var(--st-approval) 9%, var(--panel))",
            }}
          >
            <div className="text-[13px] font-semibold text-ink">
              {icon} {agent?.name ?? "Agen"}
            </div>
            <div className="my-1 mb-2.5 text-[12.5px] text-ink-soft">
              ingin menjalankan: <b className="text-ink">{r.task.desc}</b>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => approve(r.id)}
                className="flex-1 rounded-lg border border-transparent bg-st-approval py-1.5 text-center text-[12.5px] font-semibold text-[#201400]"
              >
                Setujui
              </button>
              <button
                onClick={() => reject(r.id)}
                className="flex-1 rounded-lg border border-line bg-transparent py-1.5 text-center text-[12.5px] font-semibold text-ink transition hover:border-st-error"
              >
                Tolak
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
