// HTTP client — live backend (Fase 3, BYOK). Token akses via ?token=/localStorage.
// Provider + API key LLM disimpan di localStorage (per-device); key dikirim
// per-request lewat header X-Provider-Key (tidak pernah dipersist di server).

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

const TOKEN_KEY = "octopus_token";
const PROVIDER_KEY = "octopus_provider";
const APIKEY_KEY = "octopus_apikey";

function ls(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** Token akses ruangan: dari ?token= (disimpan lalu dibersihkan), atau localStorage. */
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

// ── Provider (otak) + API key BYOK ────────────────────────────────────────────
export function getProvider(): string {
  return ls()?.getItem(PROVIDER_KEY) ?? "mock";
}
export function setProvider(p: string): void {
  ls()?.setItem(PROVIDER_KEY, p);
}
export function getApiKey(): string {
  return ls()?.getItem(APIKEY_KEY) ?? "";
}
export function setApiKey(k: string): void {
  const store = ls();
  if (!store) return;
  if (k) store.setItem(APIKEY_KEY, k);
  else store.removeItem(APIKEY_KEY);
}
/** IT-Manager "asli" aktif = provider non-mock + ada key. */
export function isRealMode(): boolean {
  return getProvider() !== "mock" && getApiKey().length > 0;
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  const h: Record<string, string> = t ? { Authorization: `Bearer ${t}` } : {};
  const key = getApiKey();
  if (key) h["X-Provider-Key"] = key;
  return h;
}

export interface CommandPayload {
  text: string;
}

/** POST perintah ke Manajer (SSE /chat/send). Best-effort; ruangan tetap hidup
 *  via /room/stream. Provider + key BYOK ikut dikirim. */
export async function sendCommand(payload: CommandPayload): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/chat/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        text: payload.text,
        as_email: "demo@local",
        provider: getProvider(),
      }),
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

export interface TaskOutcome {
  order: number;
  description: string;
  role: string;
  ok: boolean;
  detail: string;
}
export interface TaskRunResult {
  ok: boolean;
  issue_url: string;
  summary: string;
  note: string;
  outcomes: TaskOutcome[];
}

/** POST perintah ke Manajer IT (TaskRunner): PM pecah tugas → dispatch per-role
 *  ke pasukan. Progres live muncul di /room/stream; ini kembalikan hasil akhir. */
export async function runTask(request: string): Promise<TaskRunResult | null> {
  try {
    const resp = await fetch(`${API_BASE}/tasks/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        request,
        as_email: "demo@local",
        provider: getProvider(),
      }),
    });
    if (!resp.ok) return null;
    return (await resp.json()) as TaskRunResult;
  } catch {
    return null;
  }
}

async function _decide(path: string, planId: string): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ plan_id: planId, as_email: "demo@local" }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

/** Setujui plan backend yang diparkir → dieksekusi (chokepoint approved=True). */
export async function approvePlan(planId: string): Promise<boolean> {
  return _decide("/chat/approve", planId);
}

/** Tolak plan backend → dibatalkan tanpa eksekusi. */
export async function rejectPlan(planId: string): Promise<boolean> {
  return _decide("/chat/reject", planId);
}

// ── Roster pasukan (CRUD nama/peran agen) ─────────────────────────────────────

export interface RosterAgentDto {
  id: string;
  name: string;
  role: string;
}

export interface RosterMutationResult {
  ok: boolean;
  /** Pesan error server (400 validasi, dll) — cuma diisi kalau ok=false. */
  detail?: string;
}

async function _detailOf(resp: Response): Promise<string | undefined> {
  try {
    const body = (await resp.json()) as { detail?: string };
    return body.detail;
  } catch {
    return undefined;
  }
}

/** GET roster lengkap milik user (fallback roster default kalau baru pertama kali). */
export async function fetchRoster(): Promise<RosterAgentDto[] | null> {
  try {
    const resp = await fetch(`${API_BASE}/room/roster?as_email=demo@local`, {
      headers: authHeaders(),
    });
    if (!resp.ok) return null;
    return (await resp.json()) as RosterAgentDto[];
  } catch {
    return null;
  }
}

/** PUT — buat agen baru (id belum ada) atau ubah nama/peran agen yang ada. */
export async function saveAgent(
  id: string,
  data: { name: string; role: string },
): Promise<RosterMutationResult> {
  try {
    const resp = await fetch(`${API_BASE}/room/roster/${encodeURIComponent(id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ ...data, as_email: "demo@local" }),
    });
    if (!resp.ok) return { ok: false, detail: await _detailOf(resp) };
    return { ok: true };
  } catch {
    return { ok: false, detail: "gagal terhubung ke server" };
  }
}

/** DELETE agen — backend menolak (400) kalau agennya manajer. */
export async function deleteAgent(id: string): Promise<RosterMutationResult> {
  try {
    const resp = await fetch(
      `${API_BASE}/room/roster/${encodeURIComponent(id)}?as_email=demo@local`,
      { method: "DELETE", headers: authHeaders() },
    );
    if (!resp.ok) return { ok: false, detail: await _detailOf(resp) };
    const body = (await resp.json()) as { ok?: boolean };
    return body.ok === true
      ? { ok: true }
      : { ok: false, detail: "agen tidak ditemukan" };
  } catch {
    return { ok: false, detail: "gagal terhubung ke server" };
  }
}
