import { useEffect, useRef, useState } from "react";
import { MicRecorder, MicRecorderError } from "./recorder";
import { DEFAULT_VAD } from "./vad";
import { cancelSpeech } from "./tts";

export type VoiceState = "idle" | "listening" | "recording" | "transcribing";

export function VoiceBar({
  onTranscript,
  jarvis,
  onToggleJarvis,
  onListeningChange,
  vadSilenceMs = DEFAULT_VAD.silenceMs,
}: {
  onTranscript: (text: string) => void;
  jarvis: boolean;
  onToggleJarvis: () => void;
  onListeningChange?: (isListening: boolean) => void;
  vadSilenceMs?: number;
}) {
  const [state, setState] = useState<VoiceState>("idle");
  const [info, setInfo] = useState("");
  const rec = useRef<MicRecorder | null>(null);
  const stopping = useRef(false);

  useEffect(() => {
    onListeningChange?.(state === "listening" || state === "recording");
  }, [state, onListeningChange]);

  const stop = async () => {
    if (!rec.current || stopping.current) return;
    stopping.current = true;
    setState("transcribing");
    try {
      const wavB64 = await rec.current.stop();
      rec.current = null;
      const text = await window.go.main.App.Transcribe(wavB64);
      if (text) onTranscript(text);
      setState("idle");
    } catch (e) {
      setState("idle");
      setInfo(`Transkripsi gagal: ${String(e)}`);
    } finally {
      stopping.current = false;
    }
  };

  const start = async () => {
    cancelSpeech(); // barge-in: hentikan TTS yang sedang bicara (no-op bila senyap)
    setState("listening");
    setInfo("");
    stopping.current = false;
    try {
      rec.current = new MicRecorder();
      await rec.current.start({
        vad: { ...DEFAULT_VAD, silenceMs: vadSilenceMs },
        onSpeechEnd: () => void stop(),
      });
      setState("recording");
    } catch (e) {
      setState("idle");
      rec.current = null;
      if (e instanceof MicRecorderError && e.type === "permission-denied") {
        setInfo("Mikrofon tidak diizinkan — buka pengaturan browser untuk mengaktifkan suara.");
      } else {
        setInfo("Mikrofon tidak tersedia. Gunakan input teks.");
      }
    }
  };

  const toggle = () => {
    if (state === "idle") void start();
    else if (state === "recording" || state === "listening") void stop();
  };

  return (
    <div className="voice-bar">
      <button
        className={`mic-button ${state}`}
        disabled={state === "transcribing"}
        onClick={toggle}
        title={
          state === "listening"
            ? "Mendengarkan…"
            : state === "recording"
              ? "Klik untuk berhenti (otomatis berhenti saat diam)"
              : state === "transcribing"
                ? "Mentranskripsi…"
                : "Klik untuk bicara"
        }
        aria-label={
          state === "listening"
            ? "Mendengarkan"
            : state === "recording"
              ? "Merekam, klik untuk berhenti"
              : state === "transcribing"
                ? "Mentranskripsi"
                : "Mulai merekam"
        }
      >
        {state === "listening" ? "🟡" : state === "recording" ? "🔴" : state === "transcribing" ? <span className="spinner">…</span> : "🎤"}
      </button>
      {state === "recording" && (
        <div className="audio-wave">
          <span className="stroke"></span>
          <span className="stroke"></span>
          <span className="stroke"></span>
          <span className="stroke"></span>
          <span className="stroke"></span>
        </div>
      )}
      {state === "recording" && (
        <span className="listening-hint">Mendengarkan… (berhenti otomatis saat diam)</span>
      )}
      <label className="jarvis-toggle">
        <input type="checkbox" checked={jarvis} onChange={onToggleJarvis} /> Jarvis
      </label>
      {info && <span className="voice-info">{info}</span>}
    </div>
  );
}
