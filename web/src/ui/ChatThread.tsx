import { useEffect, useRef, useState } from "react";
import { useStore } from "../state/store";
import type { ChatMsg } from "../state/types";
import { cssVar, ROLE } from "../room/engine/scene";

/** Baris "panjang" mulai dilipat setelah 12 baris — cukup untuk output pendek
 *  tetap terbuka penuh, sementara jawaban agent yang panjang tak mendorong
 *  seluruh thread. */
const COLLAPSE_LINES = 12;

function CollapsibleText({ text }: { text: string }): JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const lines = text.split("\n");
  const isLong = lines.length > COLLAPSE_LINES;
  const shown = expanded || !isLong ? text : lines.slice(0, COLLAPSE_LINES).join("\n");

  return (
    <div>
      <div className="whitespace-pre-wrap break-words font-mono text-[12px] leading-snug text-ink">
        {shown}
        {isLong && !expanded && "\n…"}
      </div>
      {isLong && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-[11px] font-semibold text-accent hover:underline"
        >
          {expanded ? "Sembunyikan" : "Selengkapnya"}
        </button>
      )}
    </div>
  );
}

function UserBubble({ msg }: { msg: ChatMsg }): JSX.Element {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-3 py-2 text-accent-ink">
        <div className="whitespace-pre-wrap break-words text-[13px]">{msg.text}</div>
        <time className="mt-1 block text-right text-[10px] opacity-70">{msg.t}</time>
      </div>
    </div>
  );
}

function StatusLine({ msg }: { msg: ChatMsg }): JSX.Element {
  return (
    <div className="my-0.5 flex items-center justify-center gap-1.5 px-6 text-center text-[11px] text-ink-faint">
      {msg.ok === false && (
        <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: cssVar("error") }} />
      )}
      <span>{msg.text}</span>
      <time className="font-mono text-[10px]">{msg.t}</time>
    </div>
  );
}

function AgentBubble({ msg }: { msg: ChatMsg }): JSX.Element {
  const roleDef = msg.who === "octo" || msg.who === "user" ? ROLE.manager : ROLE[msg.who];
  const dotColor = msg.ok === undefined ? null : msg.ok ? cssVar("done") : cssVar("error");

  return (
    <div className="flex items-start gap-2">
      <div
        className="mt-0.5 flex h-7 w-7 flex-none items-center justify-center rounded-full text-[14px]"
        style={{ background: `${roleDef.color}26`, color: roleDef.color }}
        aria-hidden
      >
        {roleDef.icon}
      </div>
      <div className="max-w-[85%] min-w-0 rounded-2xl rounded-tl-sm border border-line bg-surface px-3 py-2">
        <div className="mb-1 flex items-center gap-1.5 text-[11.5px] font-semibold text-ink-soft">
          <span>{msg.name}</span>
          {dotColor && <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: dotColor }} />}
          <time className="ml-auto font-mono text-[10px] font-normal text-ink-faint">{msg.t}</time>
        </div>
        <CollapsibleText text={msg.text} />
      </div>
    </div>
  );
}

function ChatBubble({ msg }: { msg: ChatMsg }): JSX.Element {
  if (msg.kind === "user") return <UserBubble msg={msg} />;
  if (msg.kind === "status") return <StatusLine msg={msg} />;
  return <AgentBubble msg={msg} />;
}

/** Distance from the bottom (px) within which we keep auto-scrolling on new
 *  messages — beyond that the reader has scrolled up on purpose, so we leave
 *  their position alone. */
const AUTOSCROLL_THRESHOLD = 80;

/** Thread percakapan: perintahmu (kanan), jawaban tiap agen (kiri, avatar
 *  berwarna peran), ringkasan progres (baris tipis abu-abu), dan ringkasan
 *  akhir Manajer. Dipakai tab "Chat" mobile + panel "Percakapan" desktop. */
export function ChatThread(): JSX.Element {
  const chat = useStore((s) => s.chat);
  const containerRef = useRef<HTMLDivElement>(null);
  const nearBottomRef = useRef(true);

  const handleScroll = (): void => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    nearBottomRef.current = distanceFromBottom < AUTOSCROLL_THRESHOLD;
  };

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !nearBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [chat.length]);

  if (chat.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-[12.5px] text-ink-faint">
        Perintahkan Manajer lewat kolom di bawah…
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="scroll-thin flex h-full flex-col gap-2 overflow-y-auto px-3 py-3"
    >
      {chat.map((m) => (
        <ChatBubble key={m.id} msg={m} />
      ))}
    </div>
  );
}
