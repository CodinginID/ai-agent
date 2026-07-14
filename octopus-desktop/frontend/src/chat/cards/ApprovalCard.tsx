import { Tilt } from "../../components/Tilt";

export function ApprovalCard({
  planId,
  summary,
  decided,
  onApprove,
  onReject,
}: {
  planId: string;
  summary: string;
  decided: "" | "approved" | "rejected";
  onApprove: (planId: string) => void;
  onReject: (planId: string) => void;
}) {
  const disabled = decided !== "";
  return (
    <Tilt className="card card-approval">
      <div className="card-title">Butuh persetujuan</div>
      <pre className="approval-summary">{summary}</pre>
      <div className="approval-buttons">
        <button disabled={disabled} onClick={() => onApprove(planId)}>
          Approve
        </button>
        <button disabled={disabled} className="danger" onClick={() => onReject(planId)}>
          Reject
        </button>
      </div>
      {decided !== "" && <div className="approval-decided">{decided}</div>}
    </Tilt>
  );
}
