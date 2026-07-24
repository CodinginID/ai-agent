import { Tilt } from "../../components/Tilt";
import { useI18n } from "../../i18n/useI18n";

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
  const { t } = useI18n();
  const disabled = decided !== "";
  return (
    <Tilt className="card card-approval">
      <div className="card-title">{t("card_requires_approval")}</div>
      <pre className="approval-summary">{summary}</pre>
      <div className="approval-buttons">
        <button disabled={disabled} onClick={() => onApprove(planId)}>
          {t("card_approve")}
        </button>
        <button disabled={disabled} className="danger" onClick={() => onReject(planId)}>
          {t("card_reject")}
        </button>
      </div>
      {decided !== "" && <div className="approval-decided">{decided}</div>}
    </Tilt>
  );
}
