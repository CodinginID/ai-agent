import { useState, useEffect, useCallback } from "react";
import type { AvatarEvent, WorkerAvatar } from "../types";

const DEFAULT_COLORS: Record<string, string> = {
  search: "#4a90d9",
  code: "#38a169",
  plan: "#805ad5",
  monitor: "#dd6b20",
  deploy: "#e53e3e",
};

const DEFAULT_COLOR = "#4a90d9";

export function useAvatarState() {
  const [workers, setWorkers] = useState<WorkerAvatar[]>([]);

  const handleEvent = useCallback((ev: AvatarEvent) => {
    setWorkers((prev) => {
      const already = prev.find((w) => w.id === ev.workerId);

      if (ev.type === "worker:started") {
        if (already) return prev;
        return [
          ...prev,
          {
            id: ev.workerId,
            name: ev.workerName,
            type: ev.workerType,
            color: DEFAULT_COLORS[ev.workerType] ?? DEFAULT_COLOR,
            state: "working",
            task: undefined,
          },
        ];
      }

      if (ev.type === "worker:completed" || ev.type === "worker:error") {
        const newState = ev.type === "worker:error" ? "error" : "idle";
        return prev.map((w) =>
          w.id === ev.workerId
            ? {
                ...w,
                state: newState,
                task: ev.error ?? undefined,
              }
            : w,
        );
      }

      if (ev.type === "worker:progress") {
        if (!already) return prev;
        return prev.map((w) =>
          w.id === ev.workerId
            ? {
                ...w,
                task: ev.progress != null
                  ? `${Math.round(ev.progress * 100)}%`
                  : w.task,
                state: ev.error ? "error" : "working",
              }
            : w,
        );
      }

      return prev;
    });
  }, []);

  useEffect(() => {
    const handler = (e: CustomEvent<AvatarEvent>) => {
      handleEvent(e.detail);
    };
    window.addEventListener("avatar:event" as any, handler);
    return () => window.removeEventListener("avatar:event" as any, handler);
  }, [handleEvent]);

  return workers;
}
