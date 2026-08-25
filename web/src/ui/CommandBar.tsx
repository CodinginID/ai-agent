import { useState } from "react";
import { useStore } from "../state/store";
import { sendCommand } from "../net/api";

export function CommandBar(): JSX.Element {
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
    <form className="flex min-w-[200px] flex-1 gap-2" onSubmit={onSubmit} autoComplete="off">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Perintahkan Manajer… mis. 'deploy image terbaru ke VPS'"
        aria-label="Perintah untuk Manajer"
        className="min-w-0 flex-1 rounded-lg border border-line bg-surface-2 px-3 py-2 text-[13.5px] text-ink outline-none placeholder:text-ink-faint focus-visible:border-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      />
      <button
        type="submit"
        className="whitespace-nowrap rounded-lg border border-transparent bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-ink transition hover:brightness-95"
      >
        Kirim
      </button>
    </form>
  );
}
