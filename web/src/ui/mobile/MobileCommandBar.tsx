import { useState } from "react";
import { useStore } from "../../state/store";
import { sendCommand } from "../../net/api";

/** Command bar bawah ala chat: input rounded 44px + tombol kirim bulat.
 *  Submit lewat submitCommand yang sama dengan CommandBar desktop. */
export function MobileCommandBar({ autoFocus }: { autoFocus?: boolean } = {}): JSX.Element {
  const [value, setValue] = useState("");
  const submitCommand = useStore((s) => s.submitCommand);

  const onSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    const txt = value.trim();
    if (!txt) return;
    submitCommand(txt);
    void sendCommand({ text: txt }); // stub, no-op in mock mode
    setValue("");
  };

  return (
    <form
      className="flex flex-none items-center gap-2 border-t border-line bg-surface px-3 py-2"
      onSubmit={onSubmit}
      autoComplete="off"
    >
      <input
        type="text"
        autoFocus={autoFocus}
        enterKeyHint="send"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Perintahkan Manajer…"
        aria-label="Perintah untuk Manajer"
        className="h-12 min-w-0 flex-1 rounded-full border border-line bg-surface-2 px-4 text-[16px] text-ink outline-none placeholder:text-ink-faint focus-visible:border-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      />
      <button
        type="submit"
        aria-label="Kirim perintah"
        className="grid h-12 w-12 flex-none place-items-center rounded-full border border-transparent bg-accent text-accent-ink transition active:brightness-95"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="12" y1="19" x2="12" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </svg>
      </button>
    </form>
  );
}
