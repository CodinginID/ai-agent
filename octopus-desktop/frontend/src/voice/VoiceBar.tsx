import { useEffect, useRef, useState } from "react";
import { MicRecorder, MicRecorderError } from "./recorder";
import { DEFAULT_VAD } from "./vad";
import { cancelSpeech } from "./tts";
import { useI18n } from "../i18n/useI18n";

export type VoiceState = "idle" | "listening" | "recording" | "transcribing";

export function VoiceBar({
  onTranscript,
  jarvis,
  onToggleJarvis,
  onListeningChange,
  vadSilenceMs = DEFAULT_VAD.silenceMs,
  registerToggle,
}: {
  onTranscript: (text: string) => void;
  jarvis: boolean;
  onToggleJarvis: () => void;
  onListeningChange?: (isListening: boolean) => void;
  vadSilenceMs?: number;
  registerToggle?: (fn: () => void) => void;
}) {
  const { t } = useI18n();
  const [state, setState] = useState<VoiceState>("idle");
  const [info, setInfo] = useState("");
  const rec = useRef<MicRecorder | null>(null);
  const stopping = useRef(false);
  const toggleRef = useRef<() => void>(() => {});

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
      setInfo(t("voice_info_transcribe_failed", { err: String(e) }));
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
        setInfo(t("voice_info_mic_denied"));
      } else {
        setInfo(t("voice_info_mic_unavailable"));
      }
    }
  };

  const toggle = () => {
    if (state === "idle") void start();
    else if (state === "recording" || state === "listening") void stop();
  };
  toggleRef.current = toggle;

  useEffect(() => {
    registerToggle?.(() => toggleRef.current());
  }, [registerToggle]);

  return (
    <div className="voice-bar">
      <button
        className={`mic-button ${state}`}
        disabled={state === "transcribing"}
        onClick={toggle}
        title={
          state === "listening"
            ? t("voice_mic_listening")
            : state === "recording"
              ? t("voice_mic_recording")
              : state === "transcribing"
                ? t("voice_mic_transcribing")
                : t("voice_mic_idle")
        }
        aria-label={
          state === "listening"
            ? t("voice_mic_aria_listening")
            : state === "recording"
              ? t("voice_mic_aria_recording")
              : state === "transcribing"
                ? t("voice_mic_aria_transcribing")
                : t("voice_mic_aria_idle")
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
        <span className="listening-hint">{t("voice_listen_hint")}</span>
      )}
      <label className="jarvis-toggle">
        <input type="checkbox" checked={jarvis} onChange={onToggleJarvis} /> {t("voice_jarvis_label")}
      </label>
      {info && <span className="voice-info">{info}</span>}
    </div>
  );
}
