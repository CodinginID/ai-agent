import { useStore } from "../state/store";
import { ROLE, STATUS, cssVar } from "../room/engine/scene";
import { mix } from "../room/engine/render";

export function InspectorPanel(): JSX.Element {
  const agent = useStore((s) =>
    s.selectedId ? s.agents.find((a) => a.id === s.selectedId) ?? null : null,
  );

  if (!agent) {
    return (
      <p className="text-[13px] leading-relaxed text-ink-faint">
        Belum ada agen dipilih. Klik salah satu avatar di ruangan, atau pilih
        dari roster di bawah.
      </p>
    );
  }

  const role = ROLE[agent.role];
  const st = STATUS[agent.state] ?? STATUS.idle;
  const showProg = agent.state === "working" || agent.state === "review";

  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <div
          className="grid h-10 w-10 flex-none place-items-center rounded-[11px] text-[20px] shadow-[0_0_0_1px_rgba(0,0,0,.06)_inset]"
          style={{ background: mix(role.color, "#ffffff", 0.16) }}
        >
          {role.icon}
        </div>
        <div>
          <div className="text-[15px] font-semibold text-ink">{agent.name}</div>
          <div className="mt-0.5 text-[12px] text-ink-soft">{role.label}</div>
        </div>
      </div>

      <span
        className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] font-semibold"
        style={{
          color: cssVar(st.c),
          background: `color-mix(in oklab, ${cssVar(st.c)} 15%, var(--panel))`,
        }}
      >
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: "currentColor" }}
        />
        {st.txt}
      </span>

      <div className="mt-3 rounded-[10px] border border-line bg-surface-2 px-3 py-2.5 text-[13px] text-ink">
        <div className="mb-1 text-[10.5px] uppercase tracking-[.8px] text-ink-faint">
          Tugas saat ini
        </div>
        {agent.task ? agent.task.desc : "—"}
        {showProg && (
          <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-line">
            <span
              className="block h-full rounded-full bg-accent transition-[width] duration-300"
              style={{ width: `${Math.round(agent.progress * 100)}%` }}
            />
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-col gap-1.5">
        {agent.logs.length ? (
          agent.logs.map((l, i) => (
            <div key={i} className="font-mono text-[11.5px] text-ink-soft">
              <time className="text-ink-faint">{l.t}</time> · {l.msg}
            </div>
          ))
        ) : (
          <div className="text-ink-faint">Belum ada aktivitas</div>
        )}
      </div>
    </div>
  );
}
