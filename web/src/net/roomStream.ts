// Realtime room stream (Fase 3). Mock scheduler = ambience (avatar bergerak,
// task mengalir); ditambah SSE live dari backend /room/stream → feed event nyata.

import { useStore } from "../state/store";
import { getToken } from "./api";

export interface RoomStream {
  stop: () => void;
}

const STATE_POLL_MS = 20_000;

export function startRoomStream(): RoomStream {
  const stopScheduler = useStore.getState().startScheduler();
  const ctrl = new AbortController();
  void connectLive(ctrl.signal);
  // Cadangan snapshot via JSON: beberapa proxy (mis. Cloudflare quick tunnel)
  // menahan body SSE sehingga room.snapshot tak pernah sampai → roster/worker
  // di UI tetap default. /room/state = data yang sama, lewat request biasa.
  void fetchRoomState(ctrl.signal);
  const poll = window.setInterval(() => {
    if (document.visibilityState === "visible") void fetchRoomState(ctrl.signal);
  }, STATE_POLL_MS);
  return {
    stop: () => {
      stopScheduler();
      window.clearInterval(poll);
      ctrl.abort();
    },
  };
}

/** Ambil snapshot ruangan sekali (idempoten — applyServerEvent me-reconcile). */
export async function fetchRoomState(signal?: AbortSignal): Promise<boolean> {
  const token = getToken();
  if (!token) return false;
  try {
    const resp = await fetch("/room/state", {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal,
    });
    if (!resp.ok) return false;
    const ev = (await resp.json()) as Record<string, unknown>;
    useStore.getState().applyServerEvent(ev);
    return true;
  } catch {
    return false;
  }
}

/** Terima satu payload event (WS/SSE) → store. */
function applyRaw(raw: string): void {
  try {
    const ev = JSON.parse(raw) as Record<string, unknown>;
    if (ev.type === "heartbeat") return;
    useStore.getState().applyServerEvent(ev);
  } catch {
    /* abaikan payload non-JSON */
  }
}

/** Jalur utama: WebSocket /room/ws (lolos proxy yang menahan SSE, mis.
 *  Cloudflare quick tunnel). Resolve true bila pernah tersambung & menerima
 *  data, false bila gagal handshake → pemanggil fallback ke SSE. */
function connectWs(token: string, signal: AbortSignal): Promise<boolean> {
  return new Promise((resolve) => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}/room/ws?session=${encodeURIComponent(token)}`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      resolve(false);
      return;
    }
    let gotData = false;
    const onAbort = (): void => ws.close();
    signal.addEventListener("abort", onAbort, { once: true });
    ws.onmessage = (e) => {
      gotData = true;
      applyRaw(String(e.data));
    };
    ws.onerror = () => {
      /* onclose menyusul */
    };
    ws.onclose = () => {
      signal.removeEventListener("abort", onAbort);
      resolve(gotData);
    };
  });
}

async function connectLive(signal: AbortSignal): Promise<void> {
  let sseFallback = false;
  while (!signal.aborted) {
    const wsToken = getToken();
    if (wsToken && !sseFallback) {
      const ok = await connectWs(wsToken, signal);
      if (signal.aborted) return;
      // Handshake gagal (mis. proxy tak dukung WS / 401) → coba SSE di bawah;
      // pernah tersambung lalu putus → reconnect WS setelah jeda.
      if (ok) {
        await new Promise((r) => setTimeout(r, 2000));
        continue;
      }
      sseFallback = true;
    }
    // Token dibaca ulang tiap percobaan: setelah user login lewat Pengaturan
    // → Akun, stream langsung tersambung tanpa reload halaman.
    const token = getToken();
    const headers: Record<string, string> = token
      ? { Authorization: `Bearer ${token}` }
      : {};
    if (!token) {
      await new Promise((r) => setTimeout(r, 2000));
      continue;
    }
    try {
      const resp = await fetch("/room/stream", { headers, signal });
      if (!resp.ok || !resp.body) throw new Error(`room/stream HTTP ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const chunks = buf.split("\n\n");
        buf = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const dataLine = chunk
            .split("\n")
            .find((l) => l.startsWith("data:"));
          if (!dataLine) continue; // heartbeat comment / event line saja
          applyRaw(dataLine.slice(5).trim());
        }
      }
    } catch {
      if (signal.aborted) return;
    }
    // SSE putus → coba WS lagi dulu di iterasi berikutnya (mungkin sudah pulih).
    sseFallback = false;
    await new Promise((r) => setTimeout(r, 3000)); // reconnect backoff
  }
}
