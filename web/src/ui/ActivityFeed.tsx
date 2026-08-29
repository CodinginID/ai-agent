import { useEffect, useRef } from "react";
import { useStore } from "../state/store";
import { cssVar } from "../room/engine/scene";

/** `large`: tipografi mobile (14px) supaya nyaman dibaca di layar sentuh. */
export function ActivityFeed({ large }: { large?: boolean } = {}): JSX.Element {
  const events = useStore((s) => s.events);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [events.length]);

  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {events.map((f) => (
        <li key={f.id} className={`flex gap-2 leading-snug ${large ? "text-[14px]" : "text-[12.5px]"}`}>
          <span
            className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full"
            style={{ background: cssVar(f.color) }}
          />
          <span className="text-ink">
            <span dangerouslySetInnerHTML={{ __html: f.msg }} />{" "}
            <time className={`font-mono text-ink-faint ${large ? "text-[11.5px]" : "text-[10.5px]"}`}>{f.t}</time>
          </span>
        </li>
      ))}
      <div ref={endRef} />
    </ul>
  );
}
