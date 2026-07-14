import { useEffect, useState } from "react";

type Cfg = Record<string, unknown>;

interface Agent {
  id: string;
  name: string;
  enabled: boolean;
}

export function SettingsView({ onClose, onLogout }: { onClose: () => void; onLogout: () => void }) {
  const [activeTab, setActiveTab] = useState<"system" | "provider" | "agents">("system");
  const [cfg, setCfg] = useState<Cfg>({});
  const [bins, setBins] = useState<Record<string, boolean>>({});
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
      setCfg(settings);
    });

    // Get binary status
    window.go.main.App.BinaryStatus().then(setBins);

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

  const set = (k: string, v: unknown) => setCfg((c) => ({ ...c, [k]: v }));

  const save = async () => {
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
    <div className="settings-view futuristic-card">
      <div className="corner-bracket top-left"></div>
      <div className="corner-bracket top-right"></div>
      <div className="corner-bracket bottom-left"></div>
      <div className="corner-bracket bottom-right"></div>
      <div className="glow-effect"></div>
      
      <h2>PENGATURAN SYSTEM //</h2>

      <div className="settings-tabs">
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
      </div>

      {activeTab === "system" && (
        <div className="tab-content" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
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
          <div className="bin-status">
            whisper-cli: {bins.whisper ? "✅" : "❌ (install whisper.cpp / isi path di bawah)"} · piper: {bins.piper ? "✅" : "❌"}
          </div>
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
        <div className="tab-content" style={{ display: "flex", flexDirection: "column", gap: "1.2rem" }}>
          <label>
            AI Provider
            <select
              value={String(cfg.ai_provider ?? "ollama")}
              onChange={(e) => set("ai_provider", e.target.value)}
            >
              <option value="ollama">Ollama (Lokal VPS)</option>
              <option value="anthropic">Anthropic (Claude API)</option>
            </select>
          </label>

          <label>
            Model Name
            <input
              type="text"
              placeholder={cfg.ai_provider === "anthropic" ? "claude-3-5-sonnet-20241022" : "qwen2.5-coder"}
              value={String(cfg.ai_model ?? "")}
              onChange={(e) => set("ai_model", e.target.value)}
            />
          </label>

          {cfg.ai_provider === "anthropic" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem", borderLeft: "2px solid #3b82f6", paddingLeft: "1rem", marginTop: "0.5rem" }}>
              <label style={{ textTransform: "none", fontSize: "0.75rem" }}>
                <input
                  type="checkbox"
                  checked={usePersonalKey}
                  onChange={(e) => setUsePersonalKey(e.target.checked)}
                />
                Gunakan API Key Pribadi (Local Keychain)
              </label>

              {usePersonalKey && (
                <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  Claude API Key
                  <div className="password-input-container">
                    <input
                      type={showPersonalKey ? "text" : "password"}
                      placeholder="sk-ant-..."
                      value={personalKey}
                      onChange={(e) => setPersonalKey(e.target.value)}
                      style={{ background: "rgba(5, 8, 16, 0.8)", border: "1px solid var(--border-color)", borderRadius: "0.25rem", padding: "0.75rem 1rem", color: "white" }}
                    />
                    <button
                      type="button"
                      className="password-toggle-btn"
                      onClick={() => setShowPersonalKey(!showPersonalKey)}
                    >
                      {showPersonalKey ? "[ HIDE ]" : "[ SHOW ]"}
                    </button>
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "#94a3b8", textTransform: "none", marginTop: "0.25rem" }}>
                    * Disimpan aman di system keychain (OS) Anda, bukan di database VPS.
                  </span>
                </label>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === "agents" && (
        <div className="tab-content" style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
          <div style={{ fontSize: "0.75rem", color: "#94a3b8", textTransform: "none", marginBottom: "0.2rem" }}>
            Hubungkan desktop ke agent yang aktif di local worker tanpa perlu mengunduh lagi.
          </div>
          
          {loadingAgents && agents.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "#94a3b8" }}>Memuat daftar agent...</div>
          ) : agents.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "#94a3b8" }}>Tidak ada agent terdaftar.</div>
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

      <div className="settings-actions">
        <button onClick={save}>Simpan</button>
        <button onClick={onClose}>Batal</button>
        <button className="danger" onClick={onLogout}>Logout</button>
      </div>
    </div>
  );
}
