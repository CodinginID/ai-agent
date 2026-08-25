import { useEffect, useRef } from "react";
import { useStore } from "../state/store";
import { cssVar } from "../room/engine/scene";

export function ActivityFeed(): JSX.Element {
  const events = useStore((s) => s.events);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [events.length]);

  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {events.map((f) => (
        <li key={f.id} className="flex gap-2 text-[12.5px] leading-snug">
          <span
            className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full"
            style={{ background: cssVar(f.color) }}
          />
          <span className="text-ink">
            <span dangerouslySetInnerHTML={{ __html: f.msg }} />{" "}
            <time className="font-mono text-[10.5px] text-ink-faint">{f.t}</time>
          </span>
        </li>
      ))}
      <div ref={endRef} />
    </ul>
  );
}
