import { useEffect, useState, type ChangeEvent } from "react";
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

export function SettingsView({ onClose, onLogout }: { onClose: () => void; onLogout: () => void }) {
  const { t, lang, setLang } = useI18n();
  const [activeTab, setActiveTab] = useState<"system" | "voice" | "appearance" | "provider" | "agents" | "workers">("system");
  const [saving, setSaving] = useState(false);
  const [cfg, setCfg] = useState<Cfg>({});
  const [progress, setProgress] = useState<{ name: string; done: number; total: number } | null>(null);
  const [downloading, setDownloading] = useState(false);

  const [personalKey, setPersonalKey] = useState("");
  const [usePersonalKey, setUsePersonalKey] = useState(false);

  const [agents, setAgents] = useState<Agent[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);

  useEffect(() => {
    window.go.main.App.GetSettings().then((settings) => {
      setCfg(settings as unknown as Cfg);
      const savedLang = (settings as { language?: string }).language;
      if (savedLang === "en" || savedLang === "id") setLang(savedLang as "en" | "id");
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

    return window.runtime.EventsOn("assets:progress", (p) =>
      setProgress(p as { name: string; done: number; total: number }),
    );
  }, []);

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
      await window.go.main.App.ToggleAgent(agentId, !currentEnabled);
      setAgents((prev) =>
        prev.map((a) => (a.id === agentId ? { ...a, enabled: !currentEnabled } : a)),
      );
    } catch (e) {
      alert(t("agent_toggle_failed", { err: String(e) }));
    }
  };

  const set = (k: string, v: string | boolean | number) => setCfg((c) => ({ ...c, [k]: v }));

  const handleLanguageChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const code = e.target.value as "en" | "id";
    setLang(code);
    window.go.main.App.GetSettings().then((s) => {
      window.go.main.App.SaveSettings({ ...s, language: code });
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const provider = String(cfg.ai_provider || "ollama");
      const model = String(cfg.ai_model || "");

      await window.go.main.App.SaveSettings(cfg);

      try {
        await window.go.main.App.SetProvider(provider, model);
      } catch (e) {
        alert(t("setting_save_failed", { err: String(e) }));
      }

      if (provider === "anthropic" && usePersonalKey) {
        if (personalKey.trim()) {
          await window.go.main.App.SavePersonalKey(personalKey.trim());
        } else {
          await window.go.main.App.DeletePersonalKey();
        }
      } else {
        await window.go.main.App.DeletePersonalKey();
      }

      onClose();
    } finally {
      setSaving(false);
    }
  };

  const download = async () => {
    setDownloading(true);
    try {
      await window.go.main.App.DownloadAssets();
    } finally {
      setDownloading(false);
    }
  };

  const TABS: Array<{ id: typeof activeTab; label: string; icon: string }> = [
    { id: "system", label: t("tab_system"), icon: "◱" },
    { id: "voice", label: t("tab_voice"), icon: "🎙" },
    { id: "provider", label: t("tab_provider"), icon: "✦" },
    { id: "appearance", label: t("tab_appearance"), icon: "◉" },
    { id: "agents", label: `${t("tab_agents")} (${agents.filter((a) => a.enabled).length}/${agents.length})`, icon: "⛬" },
    { id: "workers", label: t("tab_workers"), icon: "⚙" },
  ];

  const ORB_SWATCHES = ["#38e1ff", "#5b8cff", "#9b7bff", "#3ddc97"];
  const vadMs = Number(cfg.vad_silence_ms) > 0 ? Number(cfg.vad_silence_ms) : 1200;

  return (
    <div className="settings-view" onClick={(e) => e.stopPropagation()}>
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
          <label>
            {t("setting_gateway_url")}
            <input value={String(cfg.gateway_url ?? "")} onChange={(e) => set("gateway_url", e.target.value)} />
          </label>
          <label>
            {t("language_label")}
            <select value={lang.code} onChange={handleLanguageChange}>
              <option value="id">{t("language_indonesian")}</option>
              <option value="en">{t("language_english")}</option>
            </select>
          </label>
          <label>
            {t("setting_whisper_bin")}
            <input value={String(cfg.whisper_bin ?? "")} onChange={(e) => set("whisper_bin", e.target.value)} />
          </label>
          <label>
            {t("setting_piper_bin")}
            <input value={String(cfg.piper_bin ?? "")} onChange={(e) => set("piper_bin", e.target.value)} />
          </label>
          <button onClick={download} disabled={downloading}>
            {downloading ? t("setting_downloading") : t("setting_download_model")}
          </button>
          {progress && (
            <progress value={progress.done} max={Math.max(progress.total, 1)}>
              {progress.name}
            </progress>
          )}
        </div>
      )}

      {activeTab === "voice" && (
        <div className="tab-content">
          <label>
            <input type="checkbox" checked={Boolean(cfg.jarvis_mode)} onChange={(e) => set("jarvis_mode", e.target.checked)} />
            {t("setting_jarvis_mode")}
          </label>
          <label>
            <input type="checkbox" checked={Boolean(cfg.tts_enabled)} onChange={(e) => set("tts_enabled", e.target.checked)} />
            {t("setting_tts_enabled")}
          </label>
          <label>
            {t("setting_vad_silence")}
            <input
              type="range"
              min={500}
              max={3000}
              step={100}
              value={vadMs}
              onChange={(e) => set("vad_silence_ms", Number(e.target.value))}
            />
            <span className="field-hint">{t("setting_vad_hint", { sec: (vadMs / 1000).toFixed(1) })}</span>
          </label>
          <label className="setting-disabled">
            <input type="checkbox" disabled />
            {t("setting_wake_word")} <span className="badge-soon">{t("badge_soon")}</span>
            <span className="field-hint">{t("setting_wake_word_desc")}</span>
          </label>
        </div>
      )}

      {activeTab === "appearance" && (
        <div className="tab-content">
          <label>
            {t("setting_orb_accent")}
            <span className="swatches">
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
            </span>
          </label>
          <label>
            <input
              type="checkbox"
              checked={Boolean(cfg.reduce_motion)}
              onChange={(e) => set("reduce_motion", e.target.checked)}
            />
            {t("setting_reduce_motion")}
          </label>
        </div>
      )}

      {activeTab === "provider" && (
        <div className="tab-content">
          <div className="setting-section">
            <h3>{t("tab_provider")}</h3>
            <p className="setting-description">
              {t("setting_provider_hint")}
            </p>
            <div className="provider-grid">
              {[
                { id: "codex", name: "OpenAI Codex" },
                { id: "claude", name: "Anthropic Claude" },
                { id: "glm", name: "GLM (Zhipu)" },
              ].map((p) => (
                <div
                  key={p.id}
                  className={`provider-option ${cfg.ai_provider === p.id ? "active" : ""}`}
                  onClick={() => set("ai_provider", p.id)}
                >
                  <div className="provider-radio">
                    {cfg.ai_provider === p.id && <div className="radio-dot" />}
                  </div>
                  <div className="provider-info">
                    <span className="provider-name">{p.name}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {cfg.ai_provider && (
            <div className="setting-section">
              <h3>{t("setting_provider_config_hint")}</h3>
              <p className="setting-description">
                {t("setting_provider_config_hint")}
              </p>
              <label>
                <span>Command</span>
                <input
                  value={String(cfg[`${cfg.ai_provider}_cmd`] ?? "")}
                  onChange={(e) => set(`${cfg.ai_provider}_cmd`, e.target.value)}
                  placeholder={t("setting_provider_cmd_placeholder", { provider: cfg.ai_provider })}
                  className="provider-cmd-input"
                />
              </label>
              <p className="field-hint">
                {t("setting_provider_cmd_hint")}
              </p>
            </div>
          )}
        </div>
      )}

      {activeTab === "agents" && (
        <div className="tab-content">
          <div className="tab-hint">
            {t("agent_tab_hint")}
          </div>

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
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={agent.enabled}
                      onChange={() => handleToggleAgent(agent.id, agent.enabled)}
                    />
                    <span className="slider"></span>
                  </label>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "workers" && (
        <div className="tab-content">
          <div className="tab-hint">
            {t("worker_tab_hint")}
          </div>
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
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={visible}
                        onChange={(e) => set(workerKey(w.type, "visible"), e.target.checked)}
                      />
                      <span className="slider"></span>
                    </label>
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

      <div className="settings-actions">
        <button className="primary" onClick={save} disabled={saving}>
          {saving ? t("setting_saving") : t("setting_save")}
        </button>
        <button onClick={onClose} disabled={saving}>{t("setting_cancel")}</button>
        <button className="danger" onClick={onLogout}>{t("setting_logout")}</button>
      </div>
      </div>
    </div>
  );
}
