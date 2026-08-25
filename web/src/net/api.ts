// STUB — HTTP client for the future backend. No live calls in P1 (mock only).
// Kept minimal so the wiring is obvious once the backend lands.

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

export interface CommandPayload {
  text: string;
}

export interface ApprovalDecision {
  approvalId: number;
  approved: boolean;
}

/** POST a natural-language command to the Manager. STUB: no-op in mock mode. */
export async function sendCommand(_payload: CommandPayload): Promise<void> {
  // TODO(phase-4): fetch(`${API_BASE}/command`, { method: "POST", ... })
  return Promise.resolve();
}

/** Resolve a pending approval. STUB: no-op in mock mode. */
export async function decideApproval(_d: ApprovalDecision): Promise<void> {
  // TODO(phase-4): fetch(`${API_BASE}/approvals/${_d.approvalId}`, ...)
  return Promise.resolve();
}
