// Realtime room stream (Fase 3). Mock scheduler = ambience (avatar bergerak,
// task mengalir); ditambah SSE live dari backend /room/stream → feed event nyata.

import { useStore } from "../state/store";
import { getToken } from "./api";

export interface RoomStream {
  stop: () => void;
}

export function startRoomStream(): RoomStream {
  const stopScheduler = useStore.getState().startScheduler();
  const ctrl = new AbortController();
  void connectLive(ctrl.signal);
  return {
    stop: () => {
      stopScheduler();
      ctrl.abort();
    },
  };
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
