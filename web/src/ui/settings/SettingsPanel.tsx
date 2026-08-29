import { useEffect, useRef, useState, type ReactNode } from "react";
import { usePushToggle } from "../../hooks/usePushToggle";
import { useIsMobile } from "../../hooks/useIsMobile";
import {
  fetchAuthConfig,
  logoutSession,
  pollGoogleLogin,
  sendTestPush,
  setToken,
  startGoogleLogin,
} from "../../net/api";
import { syncTokenToSw } from "../../net/push";
import { CURRENT_VERSION } from "../../net/version";
import { CHANGELOG } from "../../changelog";
import { useStore } from "../../state/store";
import type { Theme } from "../../state/types";
import { AgentEditor } from "../AgentEditor";
import { ProviderEditor, providerSummary } from "../ProviderSettings";

const PUSH_LABEL: Record<string, string> = {
  enabled: "aktif",
  disabled: "nonaktif",
  denied: "diblokir",
  unsupported: "tidak didukung perangkat ini",
};

const THEME_OPTIONS: { key: Theme; label: string }[] = [
  { key: "light", label: "Terang" },
  { key: "dark", label: "Gelap" },
  { key: "system", label: "Sistem" },
];

function SectionTitle({ children }: { children: ReactNode }): JSX.Element {
  return (
    <h3 className="m-0 mb-2 mt-5 font-mono text-[11px] font-semibold uppercase tracking-[1.3px] text-ink-faint first:mt-0">
      {children}
    </h3>
  );
}

function Group({ children }: { children: ReactNode }): JSX.Element {
  return (
    <div className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface-2">
      {children}
    </div>
  );
}

function Row({
  label,
  hint,
  trailing,
  onClick,
}: {
  label: ReactNode;
  hint?: ReactNode;
  trailing?: ReactNode;
  onClick?: () => void;
}): JSX.Element {
  const inner = (
    <>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] font-medium text-ink">{label}</span>
        {hint && <span className="block truncate text-[11.5px] text-ink-faint">{hint}</span>}
      </span>
      {trailing}
    </>
  );
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="flex min-h-[44px] w-full items-center gap-2 px-3 py-2 text-left transition hover:bg-surface"
      >
        {inner}
      </button>
    );
  }
  return <div className="flex min-h-[44px] items-center gap-2 px-3 py-2">{inner}</div>;
}

function Chevron(): JSX.Element {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="flex-none text-ink-faint">
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

function Switch({ checked, disabled, onClick }: { checked: boolean; disabled?: boolean; onClick: () => void }): JSX.Element {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onClick}
      className={`relative h-7 w-12 flex-none rounded-full transition disabled:opacity-40 ${
        checked ? "bg-accent" : "bg-line"
      }`}
    >
      <span
        className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-[left] ${
          checked ? "left-[22px]" : "left-0.5"
        }`}
      />
    </button>
  );
}

export interface SettingsPanelProps {
  onClose: () => void;
  /** Mobile only: pindah ke tab Pasukan + tutup Pengaturan. Kalau kosong
   *  (desktop), baris "Kelola pasukan" membuka AgentEditor langsung. */
  onNavigateToPasukan?: () => void;
}

/** Isi panel Pengaturan — dirender sebagai BottomSheet (mobile) atau modal
 *  tengah (desktop) oleh SettingsDialog. */
export function SettingsPanel({ onClose, onNavigateToPasukan }: SettingsPanelProps): JSX.Element {
  const isMobile = useIsMobile();
  const push = usePushToggle();
  const [testBusy, setTestBusy] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const theme = useStore((s) => s.theme);
  const setTheme = useStore((s) => s.setTheme);
  const agents = useStore((s) => s.agents);
  const selectedId = useStore((s) => s.selectedId);
  const update = useStore((s) => s.update);
  const checkForUpdate = useStore((s) => s.checkForUpdate);
  const applyUpdate = useStore((s) => s.applyUpdate);

  const auth = useStore((s) => s.auth);
  const refreshAuth = useStore((s) => s.refreshAuth);
  const [googleAvail, setGoogleAvail] = useState(false);
  const [tokenOpen, setTokenOpen] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [loginMsg, setLoginMsg] = useState<string | null>(null);
  const [loginBusy, setLoginBusy] = useState(false);
  const pollTimer = useRef<number | null>(null);

  useEffect(() => {
    void fetchAuthConfig().then((c) => setGoogleAvail(c.google_oauth));
    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current);
    };
  }, []);

  const finishLogin = async (token: string): Promise<void> => {
    setToken(token.trim());
    await syncTokenToSw();
    await refreshAuth();
    const st = useStore.getState().auth.status;
    setLoginMsg(st === "anon" ? "Token tidak valid" : "Berhasil masuk");
    if (st !== "anon") {
      setTokenOpen(false);
      setTokenInput("");
    }
  };

  const loginGoogle = async (): Promise<void> => {
    setLoginBusy(true);
    setLoginMsg("Membuka halaman login Google…");
    const start = await startGoogleLogin();
    if (!start) {
      setLoginBusy(false);
      setLoginMsg("Login Google belum tersedia di server ini");
      return;
    }
    window.open(start.loginUrl, "_blank", "noopener");
    setLoginMsg("Selesaikan login di tab yang terbuka — menunggu…");
    pollTimer.current = window.setInterval(() => {
      void pollGoogleLogin(start.code).then((r) => {
        if (r === "pending") return;
        if (pollTimer.current) window.clearInterval(pollTimer.current);
        pollTimer.current = null;
        setLoginBusy(false);
        if (r === "expired") setLoginMsg("Kode login kedaluwarsa, coba lagi");
        else void finishLogin(r.token);
      });
    }, 2000);
  };

  const logout = async (): Promise<void> => {
    await logoutSession();
    await refreshAuth();
    setLoginMsg(null);
  };

  const [providerOpen, setProviderOpen] = useState(false);
  const [agentEditorOpen, setAgentEditorOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [hasChecked, setHasChecked] = useState(false);

  const pushLabel = push.iosBlocked ? "butuh install di iOS" : PUSH_LABEL[push.state];

  const runTestPush = async (): Promise<void> => {
    setTestBusy(true);
    setTestResult(null);
    const res = await sendTestPush();
    setTestBusy(false);
    setTestResult(res.ok ? `Terkirim ke ${res.sent ?? 0} perangkat` : res.detail ?? "Gagal mengirim");
  };

  const runCheckForUpdate = async (): Promise<void> => {
    setHasChecked(true);
    await checkForUpdate();
  };

  const selectedAgent = agents.find((a) => a.id === selectedId) ?? null;
  const kelolaPasukan = (): void => {
    if (onNavigateToPasukan) {
      onNavigateToPasukan();
      onClose();
      return;
    }
    setAgentEditorOpen(true);
  };

  const buildDate =
    update.latest && update.latest.version === CURRENT_VERSION && update.latest.builtAt
      ? new Date(update.latest.builtAt).toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" })
      : null;

  return (
    <div className="flex flex-col">
      <SectionTitle>Akun</SectionTitle>
      <Group>
        <Row
          label={
            auth.status === "user"
              ? `Masuk sebagai ${auth.email ?? "pengguna"}`
              : auth.status === "admin"
                ? "Masuk dengan token admin"
                : auth.status === "unknown"
                  ? "Memeriksa sesi…"
                  : "Belum masuk"
          }
          hint={
            auth.status === "anon"
              ? "Persetujuan, pasukan, dan stream ruangan butuh sesi masuk"
              : loginMsg ?? undefined
          }
          trailing={
            auth.status === "anon" ? (
              <span className="h-2.5 w-2.5 flex-none rounded-full bg-st-approval" />
            ) : auth.status === "unknown" ? undefined : (
              <span className="h-2.5 w-2.5 flex-none rounded-full bg-st-done" />
            )
          }
        />
        {auth.status === "anon" && googleAvail && (
          <Row
            label={loginBusy ? "Menunggu login Google…" : "Masuk dengan Google"}
            hint={loginMsg ?? undefined}
            onClick={loginBusy ? undefined : () => void loginGoogle()}
            trailing={<Chevron />}
          />
        )}
        {auth.status === "anon" && (
          <>
            <Row
              label="Masuk dengan token akses"
              hint={tokenOpen ? undefined : "Tempel ADMIN_TOKEN / token sesi dari TUI (/login)"}
              onClick={() => setTokenOpen((v) => !v)}
              trailing={<Chevron />}
            />
            {tokenOpen && (
              <form
                className="flex items-center gap-2 px-3 py-2.5"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (tokenInput.trim()) void finishLogin(tokenInput);
                }}
              >
                <input
                  type="password"
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="Token akses"
                  autoComplete="off"
                  aria-label="Token akses"
                  className="h-11 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-[16px] text-ink outline-none focus-visible:border-accent"
                />
                <button
                  type="submit"
                  className="h-11 flex-none rounded-lg bg-accent px-4 text-[13.5px] font-semibold text-accent-ink"
                >
                  Masuk
                </button>
              </form>
            )}
            {loginMsg && !googleAvail && (
              <div className="px-3 pb-2 text-[11.5px] text-ink-faint">{loginMsg}</div>
            )}
          </>
        )}
        {(auth.status === "user" || auth.status === "admin") && (
          <Row label="Keluar" onClick={() => void logout()} trailing={<Chevron />} />
        )}
      </Group>

      <SectionTitle>Notifikasi</SectionTitle>
      <Group>
        <Row
          label="Notifikasi push"
          hint={pushLabel}
          trailing={
            <Switch
              checked={push.state === "enabled"}
              disabled={push.busy || !push.supported || push.state === "denied" || push.iosBlocked}
              onClick={() => void push.toggle()}
            />
          }
        />
        <Row
          label="Kirim notifikasi tes"
          hint={testResult ?? undefined}
          onClick={testBusy || push.state !== "enabled" ? undefined : () => void runTestPush()}
          trailing={testBusy ? <span className="text-[11px] text-ink-faint">Mengirim…</span> : undefined}
        />
      </Group>

      <SectionTitle>Otak (LLM provider)</SectionTitle>
      <Group>
        <Row
          label="Provider"
          hint={providerSummary()}
          onClick={() => setProviderOpen(true)}
          trailing={<Chevron />}
        />
      </Group>

      <SectionTitle>Tampilan</SectionTitle>
      <Group>
        <div className="flex min-h-[44px] items-center gap-2 px-3 py-2">
          <span className="mr-2 flex-none text-[13.5px] font-medium text-ink">Tema</span>
          <div className="flex flex-1 gap-1 rounded-lg bg-surface p-1">
            {THEME_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => setTheme(opt.key)}
                className={`flex-1 rounded-md py-1.5 text-[12px] font-semibold transition ${
                  theme === opt.key ? "bg-accent text-accent-ink" : "text-ink-soft"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </Group>

      <SectionTitle>Pasukan</SectionTitle>
      <Group>
        <Row
          label="Kelola pasukan"
          hint={`${agents.length} agen terdaftar`}
          onClick={kelolaPasukan}
          trailing={<Chevron />}
        />
      </Group>

      <SectionTitle>Tentang</SectionTitle>
      <Group>
        <Row label="Ruang Octopus" hint={`v${CURRENT_VERSION}${buildDate ? ` · ${buildDate}` : ""}`} />
        <Row
          label={
            update.checking
              ? "Memeriksa pembaruan…"
              : update.available
                ? "Pembaruan tersedia"
                : hasChecked
                  ? "Sudah versi terbaru"
                  : "Periksa pembaruan"
          }
          onClick={update.checking ? undefined : () => void runCheckForUpdate()}
          trailing={update.checking ? <span className="text-[11px] text-ink-faint">…</span> : undefined}
        />
        <Row
          label="Riwayat perubahan"
          onClick={() => setHistoryOpen((v) => !v)}
          trailing={<Chevron />}
        />
        {historyOpen && (
          <div className="max-h-64 overflow-y-auto bg-surface px-3 py-2">
            {CHANGELOG.map((r) => (
              <div key={r.version} className="mb-3 last:mb-0">
                <div className="font-mono text-[11px] font-semibold text-ink">
                  v{r.version} <span className="font-normal text-ink-faint">· {r.date}</span>
                </div>
                <ul className="m-0 mt-1 list-disc space-y-1 pl-4 text-[12px] text-ink-soft">
                  {r.notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Group>

      {update.available && (
        <button
          type="button"
          onClick={applyUpdate}
          className="mt-4 flex min-h-[48px] flex-col items-center justify-center rounded-xl bg-accent px-4 py-2 text-center text-[14px] font-semibold text-accent-ink"
        >
          Perbarui ke v{update.latest?.version ?? "terbaru"}
          {update.latest?.notes && update.latest.notes.length > 0 && (
            <span className="mt-1 text-[11.5px] font-normal opacity-90">
              {update.latest.notes.join(" · ")}
            </span>
          )}
        </button>
      )}

      {providerOpen && <ProviderEditor onClose={() => setProviderOpen(false)} />}
      {agentEditorOpen && (
        <AgentEditor
          agent={
            selectedAgent
              ? { id: selectedAgent.id, name: selectedAgent.name, role: selectedAgent.role }
              : null
          }
          onClose={() => setAgentEditorOpen(false)}
        />
      )}
      {!isMobile && (
        <button
          type="button"
          onClick={onClose}
          className="mt-4 min-h-[40px] rounded-lg border border-line text-[13px] font-semibold text-ink-soft"
        >
          Tutup
        </button>
      )}
    </div>
  );
}
