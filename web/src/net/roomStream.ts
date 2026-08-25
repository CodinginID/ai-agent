// STUB — realtime room stream. Phase 4 will back this with SSE (EventSource).
// In P1 the "stream" is the in-store mock scheduler; this module exposes the
// same start/stop shape the SSE client will have, so callers don't change.

import { useStore } from "../state/store";

export interface RoomStream {
  stop: () => void;
}

/**
 * Start the mock room feed. Today this just boots the in-store scheduler.
 * Later: `new EventSource(`${API_BASE}/stream`)` dispatching into the store.
 */
export function startRoomStream(): RoomStream {
  const stop = useStore.getState().startScheduler();
  return { stop };
}
