import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { useI18n } from "../i18n/useI18n";

type Cfg = {
  gateway_url?: string;
  jarvis_mode?: boolean;
  tts_enabled?: boolean;
  whisper_bin?: string;
  piper_bin?: string;
  ai_provider?: string;
  ai_model?: string;
  vad_silence_ms?: number;
  language?: string;
  orb_accent?: string;
  reduce_motion?: boolean;
} & Record<string, string | boolean | number>;

interface WorkerDef {
  type: string;
  name: string;
  defaultColor: string;
  defaultShape: string;
  defaultVisible: boolean;
}

const DEFAULT_WORKERS: WorkerDef[] = [
  { type: "engineer", name: "Engineer", defaultColor: "#4a90d9", defaultShape: "gear", defaultVisible: true },
  { type: "reviewer", name: "Reviewer", defaultColor: "#6bc99a", defaultShape: "magnifying-glass", defaultVisible: true },
  { type: "architect", name: "Architect", defaultColor: "#9b59b6", defaultShape: "blueprint", defaultVisible: true },
  { type: "server", name: "Server", defaultColor: "#f39c12", defaultShape: "server", defaultVisible: true },
  { type: "docker", name: "Docker", defaultColor: "#1abc9c", defaultShape: "container", defaultVisible: true },
  { type: "git", name: "Git", defaultColor: "#e74c3c", defaultShape: "server", defaultVisible: true },
];

const SHAPE_OPTIONS = ["gear", "magnifying-glass", "blueprint", "server", "container"];

interface Agent {
  id: string;
  name: string;
  enabled: boolean;
}

const workerKey = (type: string, field: "color" | "visible" | "shape") => `worker_${type}_${field}`;

// Backend (build_ai_provider) hanya menerima dua nilai ini.
const PROVIDERS = ["ollama", "anthropic"] as const;
type ProviderId = (typeof PROVIDERS)[number];

const ORB_SWATCHES = ["#38e1ff", "#5b8cff", "#9b7bff", "#3ddc97"];

function Toggle({
  checked,
  onChange,
  disabled = false,
  ariaLabel,
}: {
  checked: boolean;
  onChange?: (v: boolean) => void;
  disabled?: boolean;
  ariaLabel?: string;
}) {
  return (
    <label className="switch">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-label={ariaLabel}
        onChange={(e) => onChange?.(e.target.checked)}
      />
      <span className="slider"></span>
    </label>
  );
}

function Row({
  label,
  desc,
  disabled = false,
  children,
}: {
  label: ReactNode;
  desc?: ReactNode;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={`set-row ${disabled ? "disabled" : ""}`}>
      <div>
        <div className="set-row-label">{label}</div>
        {desc && <div className="set-row-desc">{desc}</div>}
      </div>
      {children}
    </div>
  );
}

function Field({ label, hint, children }: { label: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="set-field">
      <span className="set-field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </div>
  );
}

export function SettingsView({ onClose, onLogout }: { onClose: () => void; onLogout: () => void }) {
  const { t, setLang } = useI18n();
  const [activeTab, setActiveTab] = useState<"system" | "voice" | "appearance" | "provider" | "agents" | "workers">("system");
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [showToast, setShowToast] = useState(false);
  const [cfg, setCfg] = useState<Cfg>({});
  const [progress, setProgress] = useState<{ name: string; done: number; total: number } | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const [bins, setBins] = useState<Record<string, string> | null>(null);

  const [personalKey, setPersonalKey] = useState("");
  const [usePersonalKey, setUsePersonalKey] = useState(false);

  const [agents, setAgents] = useState<Agent[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [agentError, setAgentError] = useState("");

  const containerRef = useRef<HTMLDivElement | null>(null);
  const toastTimer = useRef<number>(0);

  useEffect(() => {
    // Di luar Wails (vite dev) tidak ada bridge — biarkan form kosong.
    if (!window.go?.main?.App) return;
    window.go.main.App.GetSettings().then((settings) => {
      setCfg(settings as unknown as Cfg);
    });

    window.go.main.App.GetPersonalKey().then((key) => {
      setPersonalKey(key || "");
      setUsePersonalKey(!!key);
    });

    window.go.main.App.GetProvider().then((res) => {
      if (res) {
        setCfg((c) => ({
          ...c,
          ai_provider: res.provider || c.ai_provider,
          ai_model: res.model || c.ai_model,
        }));
      }
    }).catch(() => {});

    fetchAgents();
    refreshBins();

    return window.runtime.EventsOn("assets:progress", (p) =>
      setProgress(p as { name: string; done: number; total: number }),
    );
  }, []);

  const refreshBins = () => {
    if (!window.go?.main?.App?.BinaryStatus) return;
    window.go.main.App.BinaryStatus().then(setBins).catch(() => {});
  };

  // Focus-trap sederhana: Tab berputar di dalam modal, fokus awal ke modal.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const focusables = el.querySelectorAll<HTMLElement>(
        'button, input, select, [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    el.addEventListener("keydown", trap);
    return () => el.removeEventListener("keydown", trap);
  }, []);

  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  const fetchAgents = async () => {
    try {
      setLoadingAgents(true);
      const res = await window.go.main.App.GetAgents();
      if (res && Array.isArray(res.agents)) {
        setAgents(res.agents as Agent[]);
      }
    } catch (e) {
      console.error("Failed to fetch agents:", e);
    } finally {
      setLoadingAgents(false);
    }
  };

  const handleToggleAgent = async (agentId: string, currentEnabled: boolean) => {
    try {
      setAgentError("");
      await window.go.main.App.ToggleAgent(agentId, !currentEnabled);
      setAgents((prev) =>
        prev.map((a) => (a.id === agentId ? { ...a, enabled: !currentEnabled } : a)),
      );
    } catch (e) {
      setAgentError(t("agent_toggle_failed", { err: String(e) }));
    }
  };

  const set = (k: string, v: string | boolean | number) => {
    setCfg((c) => ({ ...c, [k]: v }));
    setDirty(true);
    setSaveError("");
  };

  const handleLanguageChange = (e: ChangeEvent<HTMLSelectElement>) => {
    // Konsisten dengan field lain: berlaku & tersimpan saat Simpan.
    set("language", e.target.value);
  };

  // Nilai lama bisa berisi id CLI ("codex"/"claude") — normalisasi ke provider valid.
  const provider: ProviderId = cfg.ai_provider === "anthropic" || cfg.ai_provider === "claude" ? "anthropic" : "ollama";

  const save = async () => {
    setSaving(true);
    setSaveError("");
    try {
      await window.go.main.App.SaveSettings({ ...cfg, ai_provider: provider });
      await window.go.main.App.SetProvider(provider, String(cfg.ai_model || ""));

      if (provider === "anthropic" && usePersonalKey) {
        if (personalKey.trim()) {
          await window.go.main.App.SavePersonalKey(personalKey.trim());
        } else {
          await window.go.main.App.DeletePersonalKey();
        }
      } else {
        await window.go.main.App.DeletePersonalKey();
      }

      const code = cfg.language;
      if (code === "en" || code === "id") setLang(code);

      setDirty(false);
      setShowToast(true);
      window.clearTimeout(toastTimer.current);
      toastTimer.current = window.setTimeout(() => setShowToast(false), 2200);
    } catch (e) {
      setSaveError(t("setting_save_failed", { err: String(e) }));
    } finally {
      setSaving(false);
    }
  };

  const download = async () => {
    setDownloading(true);
    setDownloadError("");
    try {
      await window.go.main.App.DownloadAssets();
      // Backend bisa mengisi piper_bin setelah instalasi otomatis — muat ulang.
      const fresh = await window.go.main.App.GetSettings();
      setCfg((c) => ({ ...c, ...(fresh as unknown as Cfg) }));
    } catch (e) {
      setDownloadError(t("setting_download_failed", { err: String(e) }));
    } finally {
      setDownloading(false);
      refreshBins();
    }
  };

  const binStatus = (key: "whisper" | "piper") => {
    if (!bins) return null;
    const path = bins[key];
    if (path) {
      return <span className="field-hint bin-status ok">{t("setting_bin_found", { path })}</span>;
    }
    if (key === "piper" && bins.say) {
      // TTS tetap jalan lewat suara bawaan macOS — piper hanya opsional.
      return <span className="field-hint bin-status ok">{t("setting_bin_say_fallback")}</span>;
    }
    return (
      <span className="field-hint bin-status missing">
        {key === "whisper" ? t("setting_bin_missing_whisper") : t("setting_bin_missing_piper")}
      </span>
    );
  };

  const TABS: Array<{ id: typeof activeTab; label: string; icon: string }> = [
    { id: "system", label: t("tab_system"), icon: "◱" },
    { id: "voice", label: t("tab_voice"), icon: "🎙" },
    { id: "provider", label: t("tab_provider"), icon: "✦" },
    { id: "appearance", label: t("tab_appearance"), icon: "◉" },
    { id: "agents", label: `${t("tab_agents")} (${agents.filter((a) => a.enabled).length}/${agents.length})`, icon: "⛬" },
    { id: "workers", label: t("tab_workers"), icon: "⚙" },
  ];

  const vadMs = Number(cfg.vad_silence_ms) > 0 ? Number(cfg.vad_silence_ms) : 1200;

  const PROVIDER_META: Record<ProviderId, { name: string; desc: string; tag: string; tagClass: string }> = {
    ollama: { name: "Ollama", desc: t("provider_ollama_desc"), tag: t("provider_tag_local"), tagClass: "local" },
    anthropic: { name: "Anthropic Claude", desc: t("provider_anthropic_desc"), tag: t("provider_tag_cloud"), tagClass: "cloud" },
  };

  return (
    <div
      className="settings-view"
      ref={containerRef}
      tabIndex={-1}
      role="dialog"
      aria-label={t("settings_title")}
      onClick={(e) => e.stopPropagation()}
    >
      <button className="settings-x" onClick={onClose} aria-label={t("settings_close")} title={t("settings_close")}>
        ✕
      </button>

      <nav className="settings-rail">
        <h3>{t("settings_title")}</h3>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`set-tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="set-tab-icon">{tab.icon}</span> {tab.label}
          </button>
        ))}
      </nav>

      <div className="settings-body">
        <h2>{TABS.find((tab) => tab.id === activeTab)?.label}</h2>

        {activeTab === "system" && (
          <div className="tab-content">
            <Field label={t("setting_gateway_url")}>
              <input
                value={String(cfg.gateway_url ?? "")}
                placeholder="http://localhost:8080"
                onChange={(e) => set("gateway_url", e.target.value)}
              />
            </Field>
            <Field label={t("language_label")} hint={t("language_hint")}>
              <select value={String(cfg.language ?? "id")} onChange={handleLanguageChange}>
                <option value="id">{t("language_indonesian")}</option>
                <option value="en">{t("language_english")}</option>
              </select>
            </Field>
            <Field label={t("setting_whisper_bin")}>
              <input
                value={String(cfg.whisper_bin ?? "")}
                placeholder="/usr/local/bin/whisper-cli"
                onChange={(e) => set("whisper_bin", e.target.value)}
              />
              {binStatus("whisper")}
            </Field>
            <Field label={t("setting_piper_bin")}>
              <input
                value={String(cfg.piper_bin ?? "")}
                placeholder="/usr/local/bin/piper"
                onChange={(e) => set("piper_bin", e.target.value)}
              />
              {binStatus("piper")}
            </Field>
            <button onClick={download} disabled={downloading}>
              {downloading ? t("setting_downloading") : t("setting_download_model")}
            </button>
            {progress && (
              <progress value={progress.done} max={Math.max(progress.total, 1)}>
                {progress.name}
              </progress>
            )}
            {downloadError && <span className="field-hint bin-status missing">{downloadError}</span>}
          </div>
        )}

        {activeTab === "voice" && (
          <div className="tab-content">
            <Row label={t("setting_jarvis_mode_label")} desc={t("setting_jarvis_mode_desc")}>
              <Toggle
                checked={Boolean(cfg.jarvis_mode)}
                onChange={(v) => set("jarvis_mode", v)}
                ariaLabel={t("setting_jarvis_mode_label")}
              />
            </Row>
            <Row label={t("setting_tts_label")} desc={t("setting_tts_desc")}>
              <Toggle
                checked={Boolean(cfg.tts_enabled)}
                onChange={(v) => set("tts_enabled", v)}
                ariaLabel={t("setting_tts_label")}
              />
            </Row>
            <Field
              label={t("setting_vad_silence")}
              hint={t("setting_vad_hint", { sec: (vadMs / 1000).toFixed(1).replace(".", ",") })}
            >
              <div className="slider-wrap">
                <span className="slider-edge">{t("vad_min_label")}</span>
                <input
                  type="range"
                  min={500}
                  max={3000}
                  step={100}
                  value={vadMs}
                  aria-label={t("setting_vad_silence")}
                  onChange={(e) => set("vad_silence_ms", Number(e.target.value))}
                />
                <span className="slider-edge">{t("vad_max_label")}</span>
              </div>
            </Field>
            <Row
              disabled
              label={
                <>
                  {t("setting_wake_word")} <span className="badge-soon">{t("badge_soon")}</span>
                </>
              }
              desc={t("setting_wake_word_desc")}
            >
              <Toggle checked={false} disabled ariaLabel={t("setting_wake_word")} />
            </Row>
          </div>
        )}

        {activeTab === "provider" && (
          <div className="tab-content">
            <p className="setting-description">{t("setting_provider_hint")}</p>

            <div className="prov-grid" role="radiogroup" aria-label={t("tab_provider")}>
              {PROVIDERS.map((id) => {
                const meta = PROVIDER_META[id];
                const selected = provider === id;
                return (
                  <label key={id} className={`prov ${selected ? "selected" : ""}`}>
                    <input
                      type="radio"
                      name="ai-provider"
                      checked={selected}
                      onChange={() => {
                        set("ai_provider", id);
                        set("ai_model", "");
                      }}
                    />
                    <span className="prov-radio" aria-hidden="true"></span>
                    <span>
                      <span className="prov-name">{meta.name}</span>
                      <span className="prov-desc">{meta.desc}</span>
                    </span>
                    <span className={`prov-tag ${meta.tagClass}`}>{meta.tag}</span>
                  </label>
                );
              })}
            </div>

            <div className="prov-detail">
              <p className="prov-detail-title">{t("provider_options_title", { name: PROVIDER_META[provider].name })}</p>
              <Field label={t("setting_model")} hint={t("setting_model_hint")}>
                <input
                  value={String(cfg.ai_model ?? "")}
                  placeholder={provider === "ollama" ? "qwen2.5:14b" : "claude-sonnet-4-5"}
                  onChange={(e) => set("ai_model", e.target.value)}
                />
              </Field>
              {provider === "anthropic" && (
                <>
                  <Row label={t("setting_use_personal_key")} desc={t("setting_personal_key_desc")}>
                    <Toggle
                      checked={usePersonalKey}
                      onChange={(v) => {
                        setUsePersonalKey(v);
                        setDirty(true);
                      }}
                      ariaLabel={t("setting_use_personal_key")}
                    />
                  </Row>
                  {usePersonalKey && (
                    <Field label={t("setting_personal_key_label")} hint={t("setting_personal_key_hint")}>
                      <input
                        type="password"
                        value={personalKey}
                        placeholder="sk-ant-…"
                        onChange={(e) => {
                          setPersonalKey(e.target.value);
                          setDirty(true);
                        }}
                      />
                    </Field>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {activeTab === "appearance" && (
          <div className="tab-content">
            <Field label={t("setting_orb_accent")}>
              <div className="swatches">
                {ORB_SWATCHES.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`swatch ${String(cfg.orb_accent ?? "#38e1ff") === c ? "active" : ""}`}
                    style={{ backgroundColor: c }}
                    title={c}
                    aria-label={c}
                    onClick={() => set("orb_accent", c)}
                  />
                ))}
              </div>
            </Field>
            <Row label={t("setting_reduce_motion_label")} desc={t("setting_reduce_motion_desc")}>
              <Toggle
                checked={Boolean(cfg.reduce_motion)}
                onChange={(v) => set("reduce_motion", v)}
                ariaLabel={t("setting_reduce_motion_label")}
              />
            </Row>
          </div>
        )}

        {activeTab === "agents" && (
          <div className="tab-content">
            <div className="tab-hint">{t("agent_tab_hint")}</div>
            {agentError && <p className="inline-error">{agentError}</p>}

            {loadingAgents && agents.length === 0 ? (
              <div className="tab-empty">{t("agent_loading")}</div>
            ) : agents.length === 0 ? (
              <div className="tab-empty">{t("agent_none")}</div>
            ) : (
              <div className="agents-list">
                {agents.map((agent) => (
                  <div className="agent-item-card" key={agent.id}>
                    <div className="agent-info">
                      <span className="agent-name-label">{agent.name}</span>
                      <span className={`agent-status-badge ${agent.enabled ? "active" : "inactive"}`}>
                        {agent.enabled ? t("agent_connected") : t("agent_disconnected")}
                      </span>
                    </div>
                    <Toggle
                      checked={agent.enabled}
                      onChange={() => handleToggleAgent(agent.id, agent.enabled)}
                      ariaLabel={agent.name}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "workers" && (
          <div className="tab-content">
            <div className="tab-hint">{t("worker_tab_hint")}</div>
            <div className="workers-list">
              {DEFAULT_WORKERS.map((w) => {
                const color = (cfg[workerKey(w.type, "color")] as string) || w.defaultColor;
                const visible = (cfg[workerKey(w.type, "visible")] as boolean) ?? w.defaultVisible;
                const shape = (cfg[workerKey(w.type, "shape")] as string) || w.defaultShape;

                return (
                  <div className="worker-config-card" key={w.type}>
                    <div className="worker-config-header">
                      <div className="worker-config-name">
                        <div className="worker-color-dot" style={{ backgroundColor: color }}></div>
                        <span>{w.name}</span>
                      </div>
                      <Toggle
                        checked={visible}
                        onChange={(v) => set(workerKey(w.type, "visible"), v)}
                        ariaLabel={w.name}
                      />
                    </div>
                    <div className="worker-config-item">
                      <span>{t("worker_color")}</span>
                      <div className="color-picker-wrap">
                        <input
                          type="color"
                          value={color}
                          onChange={(e) => set(workerKey(w.type, "color"), e.target.value)}
                          className="worker-color-picker"
                        />
                        <span className="color-hex">{color}</span>
                      </div>
                    </div>
                    <div className="worker-config-item">
                      <span>{t("worker_shape")}</span>
                      <div className="shape-selector">
                        {SHAPE_OPTIONS.map((s) => (
                          <button
                            key={s}
                            className={`shape-btn ${shape === s ? "active" : ""}`}
                            onClick={() => set(workerKey(w.type, "shape"), s)}
                            title={s}
                          >
                            {s === "magnifying-glass" ? "🔍" :
                             s === "blueprint" ? "📐" :
                             s === "container" ? "📦" :
                             s === "server" ? "🖥" :
                             "⚙"}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {saveError && <p className="inline-error">{saveError}</p>}

        <div className="settings-actions">
          <button className={`primary ${dirty ? "dirty" : ""}`} onClick={save} disabled={saving}>
            {saving ? t("setting_saving") : t("setting_save")}
            <span className="dirty-dot" aria-hidden="true"></span>
          </button>
          <button onClick={onClose} disabled={saving}>{t("setting_cancel")}</button>
          <span className={`save-state ${dirty ? "dirty" : ""}`} role="status">
            {dirty ? t("setting_state_unsaved") : t("setting_state_saved")}
          </span>
          <button className="danger" onClick={onLogout}>{t("setting_logout")}</button>
        </div>
      </div>

      <div className={`settings-toast ${showToast ? "show" : ""}`} role="status" aria-live="polite">
        <span className="tick">✓</span> {t("setting_state_saved")}
      </div>
    </div>
  );
}
