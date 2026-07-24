import { useEffect, useState } from "react";

type Cfg = {
  gateway_url?: string;
  jarvis_mode?: boolean;
  tts_enabled?: boolean;
  whisper_bin?: string;
  piper_bin?: string;
  ai_provider?: string;
  ai_model?: string;
  vad_silence_ms?: number;
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
  const [activeTab, setActiveTab] = useState<"system" | "provider" | "agents" | "workers">("system");
  const [saving, setSaving] = useState(false);
  const [cfg, setCfg] = useState<Cfg>({});
  const [progress, setProgress] = useState<{ name: string; done: number; total: number } | null>(null);
  const [downloading, setDownloading] = useState(false);

  // AI Provider state
  const [personalKey, setPersonalKey] = useState("");
  const [usePersonalKey, setUsePersonalKey] = useState(false);
  const [showPersonalKey, setShowPersonalKey] = useState(false);

  // Agents state
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);

  useEffect(() => {
    // Get general settings
    window.go.main.App.GetSettings().then((settings) => {
      setCfg(settings as unknown as Cfg);
    });


    // Get personal key from keychain
    window.go.main.App.GetPersonalKey().then((key) => {
      setPersonalKey(key || "");
      setUsePersonalKey(!!key);
    });

    // Get provider info from server to sync (optional, settings has local copy)
    window.go.main.App.GetProvider().then((res) => {
      if (res) {
        setCfg((c) => ({
          ...c,
          ai_provider: res.provider || c.ai_provider,
          ai_model: res.model || c.ai_model,
        }));
      }
    }).catch(err => console.log("Gagal sync provider dari server:", err));

    // Fetch agents
    fetchAgents();

    // Listen to download progress
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
      console.error("Gagal mengambil daftar agent:", e);
    } finally {
      setLoadingAgents(false);
    }
  };

  const handleToggleAgent = async (agentId: string, currentEnabled: boolean) => {
    try {
      await window.go.main.App.ToggleAgent(agentId, !currentEnabled);
      // Update local state immediately
      setAgents((prev) =>
        prev.map((a) => (a.id === agentId ? { ...a, enabled: !currentEnabled } : a)),
      );
    } catch (e) {
      alert("Gagal merubah status integrasi agent: " + e);
    }
  };

  const set = (k: string, v: string | boolean | number) => setCfg((c) => ({ ...c, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      // 1. Save local general settings
      const provider = String(cfg.ai_provider || "ollama");
      const model = String(cfg.ai_model || "");

      await window.go.main.App.SaveSettings(cfg);

      // 2. Set backend AI provider preferences via SetProvider API
      try {
        await window.go.main.App.SetProvider(provider, model);
      } catch (e) {
        alert("Gagal sinkronisasi preferensi provider ke server: " + e);
      }

      // 3. Save or delete personal API key based on usePersonalKey check
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

  return (
    <div className="settings-view card">

      <h2>Pengaturan</h2>
      <p className="settings-hint">
        Klik tombol di kanan atas untuk kembali ke chat. Atau tekan <kbd>Esc</kbd>
      </p>

      <div className="settings-tabs" onClick={(e) => e.stopPropagation()}>
        <button
          className={`settings-tab-btn ${activeTab === "system" ? "active" : ""}`}
          onClick={() => setActiveTab("system")}
        >
          System
        </button>
        <button
          className={`settings-tab-btn ${activeTab === "provider" ? "active" : ""}`}
          onClick={() => setActiveTab("provider")}
        >
          AI Provider
        </button>
        <button
          className={`settings-tab-btn ${activeTab === "agents" ? "active" : ""}`}
          onClick={() => setActiveTab("agents")}
        >
          Agents ({agents.filter(a => a.enabled).length}/{agents.length})
        </button>
        <button
          className={`settings-tab-btn ${activeTab === "workers" ? "active" : ""}`}
          onClick={() => setActiveTab("workers")}
        >
          Workers
        </button>
      </div>

      {activeTab === "system" && (
        <div className="tab-content">
          <label>
            Gateway URL
            <input value={String(cfg.gateway_url ?? "")} onChange={(e) => set("gateway_url", e.target.value)} />
          </label>
          <label>
            <input type="checkbox" checked={Boolean(cfg.jarvis_mode)} onChange={(e) => set("jarvis_mode", e.target.checked)} />
            Mode Jarvis (auto-send + bacakan jawaban)
          </label>
          <label>
            <input type="checkbox" checked={Boolean(cfg.tts_enabled)} onChange={(e) => set("tts_enabled", e.target.checked)} />
            Suara balasan (TTS)
          </label>
          <label>
            Jeda hening sebelum berhenti otomatis (ms)
            <input
              type="number"
              min={500}
              max={3000}
              step={100}
              value={Number(cfg.vad_silence_ms ?? 1200)}
              onChange={(e) => set("vad_silence_ms", Number(e.target.value))}
            />
          </label>
          <label>
            Path whisper-cli
            <input value={String(cfg.whisper_bin ?? "")} onChange={(e) => set("whisper_bin", e.target.value)} />
          </label>
          <label>
            Path piper
            <input value={String(cfg.piper_bin ?? "")} onChange={(e) => set("piper_bin", e.target.value)} />
          </label>
          <button onClick={download} disabled={downloading}>
            {downloading ? "Mengunduh…" : "Unduh model (Whisper + suara Piper)"}
          </button>
          {progress && (
            <progress value={progress.done} max={Math.max(progress.total, 1)}>
              {progress.name}
            </progress>
          )}
        </div>
      )}

      {activeTab === "provider" && (
        <div className="tab-content">
          <div className="setting-section">
            <h3>AI Provider</h3>
            <p className="setting-description">
              Pilih agent CLI yang tersedia di mesin. Aplikasi akan memanggil binary langsung tanpa API key.
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
              <h3>Konfigurasi {cfg.ai_provider}</h3>
              <p className="setting-description">
                Masukkan command yang digunakan untuk mengaktifkan agent ini di terminal.
              </p>
              <label>
                <span>Command</span>
                <input
                  value={String(cfg[`${cfg.ai_provider}_cmd`] ?? "")}
                  onChange={(e) => set(`${cfg.ai_provider}_cmd`, e.target.value)}
                  placeholder={`contoh: ${cfg.ai_provider}`}
                  className="provider-cmd-input"
                />
              </label>
              <p className="field-hint">
                Command ini akan dipanggil sebagai subprocess untuk menjalankan agent CLI.
              </p>
            </div>
          )}
        </div>
      )}

      {activeTab === "agents" && (
        <div className="tab-content">
          <div className="tab-hint">
            Hubungkan desktop ke agent yang aktif di local worker tanpa perlu mengunduh lagi.
          </div>

          {loadingAgents && agents.length === 0 ? (
            <div className="tab-empty">Memuat daftar agent...</div>
          ) : agents.length === 0 ? (
            <div className="tab-empty">Tidak ada agent terdaftar.</div>
          ) : (
            <div className="agents-list">
              {agents.map((agent) => (
                <div className="agent-item-card" key={agent.id}>
                  <div className="agent-info">
                    <span className="agent-name-label">{agent.name}</span>
                    <span className={`agent-status-badge ${agent.enabled ? "active" : "inactive"}`}>
                      {agent.enabled ? "TERHUBUNG" : "TIDAK TERHUBUNG"}
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
            Sesuaikan warna dan bentuk avatar untuk setiap tipe worker.
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
                    <span>Warna</span>
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
                    <span>Bentuk</span>
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
        <button onClick={save} disabled={saving}>{saving ? "Menyimpan…" : "Simpan"}</button>
        <button onClick={onClose} disabled={saving}>Batal</button>
        <button className="danger" onClick={onLogout}>Logout</button>
      </div>
    </div>
  );
}
