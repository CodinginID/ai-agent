export type TabKey = "ruangan" | "persetujuan" | "aktivitas" | "pasukan";

const TABS: { key: TabKey; label: string }[] = [
  { key: "ruangan", label: "Ruangan" },
  { key: "persetujuan", label: "Persetujuan" },
  { key: "aktivitas", label: "Aktivitas" },
  { key: "pasukan", label: "Pasukan" },
];

const ICON_PROPS = {
  width: 22,
  height: 22,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function TabIcon({ tab }: { tab: TabKey }): JSX.Element {
  switch (tab) {
    case "ruangan":
      return (
        <svg {...ICON_PROPS}>
          <path d="M3 11.5 12 4l9 7.5" />
          <path d="M5.5 10v9h13v-9" />
        </svg>
      );
    case "persetujuan":
      return (
        <svg {...ICON_PROPS}>
          <path d="M12 3.5 5 6v6c0 4.2 3 7 7 8.5 4-1.5 7-4.3 7-8.5V6z" />
          <path d="m9.2 12.2 2 2 3.6-3.9" />
        </svg>
      );
    case "aktivitas":
      return (
        <svg {...ICON_PROPS}>
          <path d="M3 12h4l2-7 4 14 2-7h6" />
        </svg>
      );
    case "pasukan":
      return (
        <svg {...ICON_PROPS}>
          <circle cx="9" cy="8" r="3.2" />
          <path d="M2.8 19c.6-3.4 3-5.2 6.2-5.2s5.6 1.8 6.2 5.2" />
          <circle cx="17" cy="8.5" r="2.4" />
          <path d="M15.8 13.9c2.4.2 4 1.9 4.5 5" />
        </svg>
      );
    default:
      return <svg {...ICON_PROPS} />;
  }
}

export interface TabBarProps {
  active: TabKey;
  onChange: (tab: TabKey) => void;
  approvalCount: number;
  /** Rail vertikal di kiri (layar pendek/landscape) — ikon saja. */
  vertical?: boolean;
}

/** Tab bar sticky di dasar layar (4 tab) + badge angka di Persetujuan. */
export function TabBar({ active, onChange, approvalCount, vertical }: TabBarProps): JSX.Element {
  return (
    <nav
      aria-label="Navigasi utama"
      className={
        vertical
          ? "flex w-[64px] flex-none flex-col items-stretch justify-center gap-1 border-r border-line bg-surface px-1"
          : "grid flex-none grid-cols-4 border-t border-line bg-surface"
      }
      style={
        vertical
          ? { paddingLeft: "env(safe-area-inset-left)" }
          : { paddingBottom: "env(safe-area-inset-bottom)" }
      }
    >
      {TABS.map((t) => {
        const isActive = t.key === active;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            aria-label={t.label}
            aria-current={isActive ? "page" : undefined}
            className={`relative flex flex-col items-center justify-center gap-1 rounded-xl text-[11.5px] font-semibold transition ${
              vertical ? "min-h-[56px]" : "min-h-[58px]"
            } ${isActive ? "text-accent" : "text-ink-faint"}`}
          >
            <TabIcon tab={t.key} />
            {!vertical && t.label}
            {t.key === "persetujuan" && approvalCount > 0 && (
              <span className="absolute right-[22%] top-1.5 grid h-[16px] min-w-[16px] place-items-center rounded-full bg-st-error px-1 text-[9.5px] font-bold leading-none text-white">
                {approvalCount}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
