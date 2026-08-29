import { useState } from "react";
import { getProvider } from "../../net/api";
import { mix } from "../../room/engine/render";
import { ROLE, STATUS, cssVar } from "../../room/engine/scene";
import { useStore } from "../../state/store";
import type { Role } from "../../state/types";
import { AgentEditor } from "../AgentEditor";
import { InspectorPanel } from "../InspectorPanel";

type Editing = "new" | { id: string; name: string; role: Role };

/** Tab Pasukan mobile: ringkasan (worker online / LLM aktif) + roster CRUD —
 *  tap baris untuk pilih agen (InspectorPanel di bawahnya), "⋯" untuk kelola. */
export function PasukanTab(): JSX.Element {
  const agents = useStore((s) => s.agents);
  const workers = useStore((s) => s.workers);
  const selectedId = useStore((s) => s.selectedId);
  const select = useStore((s) => s.select);
  const [editing, setEditing] = useState<Editing | null>(null);

  return (
    <div className="scroll-thin h-full overflow-y-auto px-3 py-3">
      <div className="mb-3 grid grid-cols-2 gap-2.5">
        <div className="rounded-xl border border-line bg-surface-2 p-3">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">
            Worker online
          </div>
          <div className="mt-1 font-display text-[20px] font-bold text-ink">{workers}</div>
        </div>
        <div className="rounded-xl border border-line bg-surface-2 p-3">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">LLM aktif</div>
          <div className="mt-1 truncate font-display text-[16px] font-bold text-ink">
            {getProvider()}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        {agents.map((a) => {
          const active = a.id === selectedId;
          const st = STATUS[a.state] ?? STATUS.idle;
          return (
            <div key={a.id}>
              <div
                className={`flex min-h-[56px] items-center gap-2 rounded-xl border px-2.5 ${
                  active ? "border-accent bg-surface-2" : "border-line bg-surface"
                }`}
              >
                <button
                  type="button"
                  onClick={() => select(active ? null : a.id)}
                  className="flex min-w-0 flex-1 items-center gap-3 py-2 text-left"
                >
                  <span
                    className="grid h-10 w-10 flex-none place-items-center rounded-full text-[16px]"
                    style={{ background: mix(ROLE[a.role].color, "#ffffff", 0.16) }}
                  >
                    {ROLE[a.role].icon}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-semibold text-ink">
                      {a.name}{" "}
                      <span className="font-normal text-ink-faint">
                        · {ROLE[a.role].label}
                      </span>
                    </span>
                    <span className="block truncate text-[12.5px] text-ink-soft">
                      {a.task ? a.task.desc : "—"}
                    </span>
                  </span>
                </button>
                <span
                  className="flex-none font-mono text-[11px]"
                  style={{ color: cssVar(st.c) }}
                >
                  {st.txt}
                </span>
                <button
                  type="button"
                  onClick={() => setEditing({ id: a.id, name: a.name, role: a.role })}
                  aria-label={`Kelola ${a.name}`}
                  className="grid h-11 w-11 flex-none place-items-center rounded-lg text-[18px] text-ink-faint"
                >
                  ⋯
                </button>
              </div>
              {active && (
                <div className="mb-1 mt-1.5 rounded-xl border border-line bg-panel p-3">
                  <InspectorPanel />
                </div>
              )}
            </div>
          );
        })}

        <button
          type="button"
          onClick={() => setEditing("new")}
          className="mt-1 min-h-[52px] rounded-xl border border-dashed border-line text-[14.5px] font-semibold text-ink-soft"
        >
          + Tambah agen
        </button>
      </div>

      {editing && (
        <AgentEditor
          agent={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
