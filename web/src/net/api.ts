// HTTP client — live backend (Fase 3). Token via ?token= di URL atau localStorage.
// Frontend & backend disajikan satu origin lewat proxy Vite, jadi path relatif.

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

const TOKEN_KEY = "octopus_token";

/** Ambil token: dari ?token= (disimpan ke localStorage lalu dibersihkan dari URL), atau localStorage. */
export function getToken(): string {
  if (typeof window === "undefined") return "";
  try {
    const url = new URL(window.location.href);
    const q = url.searchParams.get("token");
    if (q) {
      window.localStorage.setItem(TOKEN_KEY, q);
      url.searchParams.delete("token");
      window.history.replaceState({}, "", url.toString());
      return q;
    }
    return window.localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export interface CommandPayload {
  text: string;
}

/** POST perintah ke Manajer (SSE /chat/send). Best-effort: kalau gagal, diam
 *  (ruangan tetap hidup via mock + /room/stream). Stream di-drain sampai selesai
 *  supaya backend memproses penuh; event balik muncul lewat /room/stream. */
export async function sendCommand(payload: CommandPayload): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/chat/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ text: payload.text, as_email: "demo@local" }),
    });
    if (!resp.ok || !resp.body) return false;
    const reader = resp.body.getReader();
    for (;;) {
      const { done } = await reader.read();
      if (done) break;
    }
    return true;
  } catch {
    return false;
  }
}

export interface ApprovalDecision {
  approvalId: number;
  approved: boolean;
}

/** Approve LIVE via web menyusul (endpoint belum ada) — no-op sekarang. */
export async function decideApproval(_d: ApprovalDecision): Promise<void> {
  return Promise.resolve();
}
