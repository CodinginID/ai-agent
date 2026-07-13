import { useEffect, useState } from "react";

type Cfg = Record<string, unknown>;

export function SettingsView({ onClose, onLogout }: { onClose: () => void; onLogout: () => void }) {
  const [cfg, setCfg] = useState<Cfg>({});
  const [bins, setBins] = useState<Record<string, boolean>>({});
  const [progress, setProgress] = useState<{ name: string; done: number; total: number } | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    window.go.main.App.GetSettings().then(setCfg);
    window.go.main.App.BinaryStatus().then(setBins);
    return window.runtime.EventsOn("assets:progress", (p) =>
      setProgress(p as { name: string; done: number; total: number }),
    );
  }, []);

  const set = (k: string, v: unknown) => setCfg((c) => ({ ...c, [k]: v }));

  const save = async () => {
    await window.go.main.App.SaveSettings(cfg);
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
      <div className="settings-actions">
        <button onClick={save}>Simpan</button>
        <button onClick={onClose}>Batal</button>
        <button className="danger" onClick={onLogout}>Logout</button>
      </div>
    </div>
  );
}
