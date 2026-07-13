import { useRef, useState } from "react";
import { MicRecorder } from "./recorder";

export function VoiceBar({
  onTranscript,
  jarvis,
  onToggleJarvis,
}: {
  onTranscript: (text: string) => void;
  jarvis: boolean;
  onToggleJarvis: () => void;
}) {
  const [state, setState] = useState<"idle" | "recording" | "transcribing" | "unavailable">("idle");
  const [error, setError] = useState("");
  const rec = useRef<MicRecorder | null>(null);

  const start = async () => {
    try {
      rec.current = new MicRecorder();
      await rec.current.start();
      setState("recording");
      setError("");
    } catch {
      setState("unavailable");
      setError("Mic tidak tersedia atau izin ditolak — pakai input teks.");
    }
  };

  const stop = async () => {
    if (!rec.current) return;
    setState("transcribing");
    try {
      const wavB64 = await rec.current.stop();
      const text = await window.go.main.App.Transcribe(wavB64);
      if (text) onTranscript(text);
      setState("idle");
    } catch (e) {
      setState("idle");
      setError(`Transkripsi gagal: ${String(e)}`);
    }
  };

  return (
    <div className="voice-bar">
      <button
        className={`mic-button ${state}`}
        disabled={state === "transcribing" || state === "unavailable"}
        onMouseDown={start}
        onMouseUp={stop}
        title="Tahan untuk bicara"
      >
        {state === "recording" ? "🔴" : state === "transcribing" ? "…" : "🎤"}
      </button>
      <label className="jarvis-toggle">
        <input type="checkbox" checked={jarvis} onChange={onToggleJarvis} /> Jarvis
      </label>
      {error && <span className="voice-error">{error}</span>}
    </div>
  );
}
