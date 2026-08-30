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

async function connectLive(signal: AbortSignal): Promise<void> {
  while (!signal.aborted) {
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
          try {
            const ev = JSON.parse(dataLine.slice(5).trim());
            useStore.getState().applyServerEvent(ev);
          } catch {
            /* abaikan payload non-JSON */
          }
        }
      }
    } catch {
      if (signal.aborted) return;
    }
    await new Promise((r) => setTimeout(r, 3000)); // reconnect backoff
  }
}
