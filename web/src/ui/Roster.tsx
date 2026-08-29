import { useState } from "react";
import { useStore } from "../state/store";
import { ROLE, STATUS, cssVar } from "../room/engine/scene";
import { AgentEditor } from "./AgentEditor";

export function Roster(): JSX.Element {
  const agents = useStore((s) => s.agents);
  const selectedId = useStore((s) => s.selectedId);
  const select = useStore((s) => s.select);
  const [editing, setEditing] = useState(false);
  const selectedAgent = agents.find((a) => a.id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="rounded-md border border-line px-2 py-1 text-[11px] font-semibold text-ink-soft transition hover:border-accent hover:text-ink"
        >
          Kelola
        </button>
      </div>

      <div className="flex flex-col gap-0.5">
        {agents.map((a) => {
          const st = STATUS[a.state] ?? STATUS.idle;
          const active = a.id === selectedId;
          return (
            <button
              key={a.id}
              onClick={() => select(a.id)}
              className={`flex items-center gap-2.5 rounded-lg border px-2 py-1.5 text-left transition ${
                active
                  ? "border-line bg-surface-2"
                  : "border-transparent hover:bg-surface-2"
              }`}
            >
              <span
                className="h-2.5 w-2.5 flex-none rounded-full"
                style={{ background: ROLE[a.role].color }}
              />
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink">
                {a.name}{" "}
                <span className="font-normal text-ink-faint">
                  · {ROLE[a.role].label}
                </span>
              </span>
              <span
                className="font-mono text-[10.5px]"
                style={{ color: cssVar(st.c) }}
              >
                {st.txt}
              </span>
            </button>
          );
        })}
      </div>

      {editing && (
        <AgentEditor
          agent={
            selectedAgent
              ? { id: selectedAgent.id, name: selectedAgent.name, role: selectedAgent.role }
              : null
          }
          onClose={() => setEditing(false)}
        />
      )}
    </div>
  );
}
