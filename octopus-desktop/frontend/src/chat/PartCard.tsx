import type { Part } from "./types";
import { ActionCard } from "./cards/ActionCard";
import { ApprovalCard } from "./cards/ApprovalCard";
import { ErrorCard } from "./cards/ErrorCard";
import { MetricCard } from "./cards/MetricCard";
import { StatusLine } from "./cards/StatusLine";
import { TableCard } from "./cards/TableCard";
import { TextCard } from "./cards/TextCard";

const METRIC_ACTIONS = new Set(["memory", "disk", "server_status", "docker_stats"]);
const TABLE_ACTIONS = new Set(["docker_ps", "docker_images", "docker_compose_ps", "processes"]);

export interface PartCardProps {
  part: Part;
  onApprove?: (planId: string) => void;
  onReject?: (planId: string) => void;
  onRetry?: () => void;
}

// Merender satu Part ke kartu yang sesuai. Dipakai DataPanel (orb-centric)
// dan ChatView (chat-log lama).
export function PartCard({ part: p, onApprove, onReject, onRetry }: PartCardProps) {
  switch (p.kind) {
    case "status":
      return <StatusLine text={p.text} />;
    case "text":
      return <TextCard text={p.text} streaming={p.streaming} />;
    case "action":
      if (!p.running && METRIC_ACTIONS.has(p.action))
        return <MetricCard action={p.action} output={p.output} />;
      if (!p.running && TABLE_ACTIONS.has(p.action))
        return <TableCard action={p.action} output={p.output} />;
      return <ActionCard action={p.action} running={p.running} output={p.output} />;
    case "approval":
      return (
        <ApprovalCard
          planId={p.planId}
          summary={p.summary}
          decided={p.decided}
          onApprove={(id) => onApprove?.(id)}
          onReject={(id) => onReject?.(id)}
        />
      );
    case "error":
      return <ErrorCard message={p.message} retryable={p.retryable} onRetry={() => onRetry?.()} />;
  }
}
