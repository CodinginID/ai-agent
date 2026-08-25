import { useStore } from "../state/store";
import { ROLE, STATUS, cssVar } from "../room/engine/scene";

export function Roster(): JSX.Element {
  const agents = useStore((s) => s.agents);
  const selectedId = useStore((s) => s.selectedId);
  const select = useStore((s) => s.select);

  return (
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
  );
}
