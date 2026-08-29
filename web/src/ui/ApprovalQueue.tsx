import { ROLE } from "../room/engine/scene";
import { useStore } from "../state/store";
import { useIsMobile } from "../hooks/useIsMobile";
import { ApprovalCard } from "./ApprovalCard";

export function ApprovalQueue(): JSX.Element {
  const approvals = useStore((s) => s.approvals);
  const serverApprovals = useStore((s) => s.serverApprovals);
  const agents = useStore((s) => s.agents);
  const approve = useStore((s) => s.approve);
  const reject = useStore((s) => s.reject);
  const approveServer = useStore((s) => s.approveServer);
  const rejectServer = useStore((s) => s.rejectServer);
  // Tab Persetujuan / ApprovalSheet mobile butuh target sentuh >=48px.
  const tall = useIsMobile();

  if (!approvals.length && !serverApprovals.length) {
    return (
      <p className="text-[12.5px] text-ink-faint">
        Tidak ada permintaan. Aksi berisiko akan muncul di sini.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2.5">
      {/* Approval backend nyata (dari /room/stream) */}
      {serverApprovals.map((r) => (
        <ApprovalCard
          key={r.planId}
          title="🛰️ Backend"
          desc={r.desc}
          tall={tall}
          onApprove={() => approveServer(r.planId)}
          onReject={() => rejectServer(r.planId)}
        />
      ))}

      {/* Approval mock (ambience scheduler) */}
      {approvals.map((r) => {
        const agent = agents.find((a) => a.id === r.agentId);
        const icon = agent ? ROLE[agent.role].icon : "⚙";
        return (
          <ApprovalCard
            key={r.id}
            title={`${icon} ${agent?.name ?? "Agen"}`}
            desc={
              <>
                ingin menjalankan: <b className="text-ink">{r.task.desc}</b>
              </>
            }
            tall={tall}
            onApprove={() => approve(r.id)}
            onReject={() => reject(r.id)}
          />
        );
      })}
    </div>
  );
}
