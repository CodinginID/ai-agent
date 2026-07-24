import { useEffect, useRef, useState } from "react";
import { VoiceBar } from "./voice/VoiceBar";
import { speak } from "./voice/tts";
import { LoginView } from "./setup/LoginView";
import { SettingsView } from "./setup/SettingsView";
import { useI18n } from "./i18n/useI18n";
import { OrbStage } from "./orb/OrbStage";
import { ResponseLayer } from "./chat/ResponseLayer";
import { DataPanel } from "./chat/DataPanel";
import { InputDock } from "./chat/InputDock";
import { HistoryDrawer } from "./chat/HistoryDrawer";
import { useChat } from "./chat/useChat";
import { deriveAiState } from "./orb/orbState";
import "./style.css";

const ESCAPE_KEY = "Escape";

export default function App() {
  const [screen, setScreen] = useState<"loading" | "login" | "chat">("loading");
  const [showSettings, setShowSettings] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [jarvis, setJarvis] = useState(true);
  const [vadSilenceMs, setVadSilenceMs] = useState(1200);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [amplitude, setAmplitude] = useState(0);
  const [dismissedData, setDismissedData] = useState("");

  const chat = useChat();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const voiceToggle = useRef<() => void>(() => {});
  const lastSpokenRef = useRef("");

  const aiState = deriveAiState(chat.pending, isSpeaking, isListening);

  const textParts = (chat.current?.parts ?? []).filter((p) => p.kind === "text");
  const responseText = textParts.map((p) => (p.kind === "text" ? p.text : "")).join("\n");
  const streaming = !!chat.current && !chat.current.done;
  const dataParts = chat.current && chat.current.msgId !== dismissedData ? chat.current.parts : [];

  // TTS untuk jawaban final (mode Jarvis)
  useEffect(() => {
    const c = chat.current;
    if (!jarvis || !c?.done || !c.finalText || c.finalText === lastSpokenRef.current) return;
    lastSpokenRef.current = c.finalText;
    setIsSpeaking(true);
    void speak(c.finalText, (lvl) => setAmplitude(lvl))
      .catch(() => {}) // TTS gagal tidak boleh ganggu chat
      .finally(() => {
        setIsSpeaking(false);
        setAmplitude(0);
      });
  }, [chat.current?.done, chat.current?.finalText, jarvis]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === ESCAPE_KEY) {
        if (showSettings) return setShowSettings(false);
        if (showHistory) return setShowHistory(false);
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "k" && screen === "chat") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showSettings, showHistory, screen]);

  useEffect(() => {
    if (!window.go || !window.go.main.App) {
      console.error("Wails runtime not loaded - this should not happen in production!");
      setScreen("chat");
      return;
    }
    window.go.main.App.IsLoggedIn()
      .then((loggedIn) => setScreen(loggedIn ? "chat" : "login"))
      .catch((err) => {
        console.error("Failed to check login status:", err);
        setScreen("chat");
      });
  }, []);

  useEffect(() => {
    if (screen !== "chat" || !window.go?.main?.App) return;
    window.go.main.App.GetSettings().then((s) => {
      setJarvis(Boolean(s.jarvis_mode));
      const ms = Number((s as { vad_silence_ms?: number }).vad_silence_ms);
      if (Number.isFinite(ms) && ms > 0) setVadSilenceMs(ms);
    });
  }, [screen]);

  const handleTranscript = (text: string) => {
    if (jarvis) chat.submit(text);
    else window.dispatchEvent(new CustomEvent("voice:draft", { detail: text }));
  };

  const toggleJarvis = () => {
    const next = !jarvis;
    setJarvis(next);
    window.go.main.App.GetSettings().then((s) => window.go.main.App.SaveSettings({ ...s, jarvis_mode: next }));
  };

  const handleLogout = async () => {
    await window.go.main.App.Logout();
    setShowSettings(false);
    setScreen("login");
  };

  const { t } = useI18n();
  if (screen === "loading") return <div className="loading-screen">{t("loading")}</div>;
  if (screen === "login") return <LoginView onPaired={() => setScreen("chat")} />;

  return (
    <div className="orb-app">
      <span className="hud-corner tl" aria-hidden="true" />
      <span className="hud-corner tr" aria-hidden="true" />
      <span className="hud-corner bl" aria-hidden="true" />
      <span className="hud-corner br" aria-hidden="true" />

      <div className="brand">
        <span className="brand-dot" aria-hidden="true" />
        Octopus
      </div>
      <div className="orb-header-actions">
        <button
          className="hud-icon-btn"
          onClick={() => setShowHistory(true)}
          aria-label={t("history_title")}
          title={t("history_title")}
        >
          ⏱
        </button>
        <button
          className="hud-icon-btn hud-gear"
          onClick={() => setShowSettings(true)}
          aria-label={t("settings_title")}
          title={t("settings_title")}
        >
          ⚙
        </button>
      </div>

      <main className="orb-main">
        <OrbStage
          state={aiState}
          amplitude={amplitude}
          paused={showSettings}
          onActivate={() => voiceToggle.current()}
        >
          <ResponseLayer text={responseText} streaming={streaming} />
        </OrbStage>

        <DataPanel
          parts={dataParts}
          onClose={() => chat.current && setDismissedData(chat.current.msgId)}
          onApprove={(id) => chat.current && chat.decide(chat.current, id, "approved")}
          onReject={(id) => chat.current && chat.decide(chat.current, id, "rejected")}
          onRetry={() => chat.retryLast((t) => chat.submit(t))}
        />
      </main>

      <InputDock
        ref={inputRef}
        onSubmit={chat.submit}
        voiceSlot={
          <VoiceBar
            onTranscript={handleTranscript}
            vadSilenceMs={vadSilenceMs}
            jarvis={jarvis}
            onToggleJarvis={toggleJarvis}
            onListeningChange={setIsListening}
            registerToggle={(fn) => (voiceToggle.current = fn)}
          />
        }
      />

      <HistoryDrawer open={showHistory} onClose={() => setShowHistory(false)} messages={chat.messages} />

      {showSettings && (
        <div
          className="modal-overlay"
          onClick={(e) => e.target === e.currentTarget && setShowSettings(false)}
        >
          <div className="modal-container" onClick={(e) => e.stopPropagation()}>
            <SettingsView onClose={() => setShowSettings(false)} onLogout={handleLogout} />
          </div>
        </div>
      )}
    </div>
  );
}
