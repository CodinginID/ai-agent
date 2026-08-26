import { useStore } from "../state/store";
import { CommandBar } from "./CommandBar";
import { ProviderButton } from "./ProviderSettings";

export function TopBar(): JSX.Element {
  const count = useStore((s) => s.agents.length);
  const workers = useStore((s) => s.workers);
  const theme = useStore((s) => s.theme);
  const toggleTheme = useStore((s) => s.toggleTheme);

  return (
    <header className="flex flex-wrap items-center gap-4 border-b border-line bg-surface px-4 py-2.5">
      <div className="flex min-w-0 items-center gap-2.5">
        <div className="grid h-[34px] w-[34px] place-items-center rounded-[9px] bg-gradient-to-br from-accent to-[#6b5bd6] text-[19px] shadow-[0_0_0_1px_rgba(56,225,198,.4)_inset]">
          🐙
        </div>
        <div>
          <h1 className="m-0 whitespace-nowrap font-display text-[17px] font-bold leading-none tracking-[.3px] text-ink">
            Ruang Octopus
          </h1>
          <div className="mt-[3px] hidden whitespace-nowrap text-[11px] tracking-[.3px] text-ink-faint sm:block">
            AI IT-Manager &amp; pasukan agen — prototipe gather-room
          </div>
        </div>
      </div>

      <CommandBar />

      <div className="flex items-center gap-1.5 whitespace-nowrap font-mono text-[12px] text-ink-soft">
        <span className="h-[7px] w-[7px] rounded-full bg-accent shadow-[0_0_8px_var(--accent)]" />
        {count} agen
      </div>

      <div
        className="flex items-center gap-1.5 whitespace-nowrap font-mono text-[12px] text-ink-soft"
        title="Pasukan (worker) yang terhubung ke backend"
      >
        <span
          className={
            workers > 0
              ? "h-[7px] w-[7px] rounded-full bg-[#3ddc84] shadow-[0_0_8px_#3ddc84]"
              : "h-[7px] w-[7px] rounded-full bg-ink-faint"
          }
        />
        {workers} pasukan
      </div>

      <ProviderButton />

      <button
        type="button"
        title="Ganti tema"
        aria-label="Ganti tema"
        onClick={toggleTheme}
        className="rounded-lg border border-line bg-surface-2 px-2.5 py-2 text-[13px] font-semibold text-ink transition hover:border-accent"
      >
        {theme === "dark" ? "☀" : "◐"}
      </button>
    </header>
  );
}
