import { useEffect, useRef, useState, useCallback } from "react";
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

// Skip-link anchors — harus ada sebelum konten utama agar screen reader langsung bisa jump.
const SKIP_MAIN_ID = "skip-main-content";
const SKIP_NAV_ID = "skip-navigation";

export default function App() {
  const [screen, setScreen] = useState<"loading" | "login" | "chat">("loading");
  const [showSettings, setShowSettings] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [jarvis, setJarvis] = useState(true);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [voiceNotice, setVoiceNotice] = useState("");
  const [vadSilenceMs, setVadSilenceMs] = useState(1200);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [amplitude, setAmplitude] = useState(0);
  const [dismissedData, setDismissedData] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const { t } = useI18n();
  const chat = useChat();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const gearRef = useRef<HTMLButtonElement | null>(null);
  const voiceToggle = useRef<() => void>(() => {});
  const lastSpokenRef = useRef("");
  const voiceLabelRef = useRef<"idle" | "listening">("idle");

  const aiState = deriveAiState(chat.pending, isSpeaking, isListening);

  const textParts = (chat.current?.parts ?? []).filter((p) => p.kind === "text");
  const responseText = textParts.map((p) => (p.kind === "text" ? p.text : "")).join("\n");
  const streaming = !!chat.current && !chat.current.done;
  const dataParts = chat.current && chat.current.msgId !== dismissedData ? chat.current.parts : [];

  // TTS untuk jawaban final (mode Jarvis). Kegagalan tidak boleh ganggu
  // chat, tapi wajib terlihat — tampilkan notice singkat, jangan ditelan.
  useEffect(() => {
    const c = chat.current;
    if (!jarvis || !ttsEnabled || !c?.done || !c.finalText || c.finalText === lastSpokenRef.current) return;
    lastSpokenRef.current = c.finalText;
    setIsSpeaking(true);
    void speak(c.finalText, (lvl) => setAmplitude(lvl))
      .catch((e) => setVoiceNotice(t("voice_info_tts_failed", { err: String(e) })))
      .finally(() => {
        setIsSpeaking(false);
        setAmplitude(0);
      });
  }, [chat.current?.done, chat.current?.finalText, jarvis, ttsEnabled]);

  useEffect(() => {
    if (!voiceNotice) return;
    const id = window.setTimeout(() => setVoiceNotice(""), 6000);
    return () => window.clearTimeout(id);
  }, [voiceNotice]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === ESCAPE_KEY) {
        if (showSettings) return closeSettings();
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
      setTtsEnabled(Boolean((s as { tts_enabled?: boolean }).tts_enabled));
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

  const closeSettings = () => {
    setShowSettings(false);
    gearRef.current?.focus();
  };

  // Update voice button label based on state
  useEffect(() => {
    voiceLabelRef.current = isListening ? "listening" : "idle";
  }, [isListening]);

  const handleVoiceToggle = useCallback(() => {
    voiceLabelRef.current = isListening ? "idle" : "listening";
    voiceToggle.current();
  }, [isListening]);

  const handleLogout = async () => {
    await window.go.main.App.Logout();
    setShowSettings(false);
    setScreen("login");
  };

  if (screen === "loading") return <div className="loading-screen">{t("loading")}</div>;
  if (screen === "login") return <LoginView onPaired={() => setScreen("chat")} />;

  return (
    <div className="orb-app">
      {/* Skip links — fokus langsung ke konten utama atau navigasi tanpa harus tab satu per satu */}
      <a href={`#${SKIP_MAIN_ID}`} className="skip-link">
        {t("skip_to_main_content")}
      </a>
      <a href={`#${SKIP_NAV_ID}`} className="skip-link">
        {t("skip_to_navigation")}
      </a>

      <span className="hud-corner tl" aria-hidden="true" />
      <span className="hud-corner tr" aria-hidden="true" />
      <span className="hud-corner bl" aria-hidden="true" />
      <span className="hud-corner br" aria-hidden="true" />

      {/* Header navigasi — brand + tombol aksi */}
      <div className="brand" id={SKIP_NAV_ID} aria-label={t("brand_name")}>
        <span className="brand-dot" aria-hidden="true" />
        Octopus
      </div>
      <nav className="orb-header-actions" role="navigation" aria-label={t("header_nav")}>
        <button
          className="hud-icon-btn"
          onClick={() => setShowHistory(true)}
          aria-label={t("history_title")}
          title={t("history_title")}
        >
          ⏱
        </button>
        <button
          ref={gearRef}
          className="hud-icon-btn hud-gear"
          onClick={() => setShowSettings(true)}
          aria-label={t("settings_title")}
          title={t("settings_title")}
        >
          ⚙
        </button>
      </nav>

      {/* Main chat area */}
      <main
        id={SKIP_MAIN_ID}
        className="orb-main"
        role="main"
        aria-label={t("chat_main")}
      >
        <OrbStage
          state={aiState}
          amplitude={amplitude}
          paused={showSettings}
          onActivate={() => voiceToggle.current()}
        >
          {/* aria-live region untuk respon AI — pembaca layar akan membaca update secara dinamis */}
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

      {/* Input dock — navigasi keyboard: tab dari voice ke input, enter kirim */}
      <InputDock
        ref={inputRef}
        onSubmit={chat.submit}
        voiceSlot={
          <VoiceBar
            onTranscript={handleTranscript}
            vadSilenceMs={vadSilenceMs}
            jarvis={jarvis}
            onToggleJarvis={toggleJarvis}
            onListeningChange={(listening) => {
              setIsListening(listening);
              if (!listening) {
                voiceLabelRef.current = "idle";
              }
            }}
            registerToggle={(fn) => (voiceToggle.current = fn)}
          />
        }
        onSubmitLabel={t("chat_send_aria")}
      />

      {/* Voice notice dengan aria-live polite agar screen reader memberitahu tanpa interrupt */}
      {voiceNotice && (
        <div className="voice-notice" role="alert" aria-live="polite">
          {voiceNotice}
        </div>
      )}

      {/* aria-live region untuk dynamic announcements (chat send, voice state changes) */}
      <div aria-live="polite" aria-atomic="true" className="sr-only" role="status">
        {isBusy && t("loading")}
        {!chat.current?.done && chat.current?.parts?.length !== undefined && streaming
          ? t("response_streaming")
          : ""}
      </div>

      <HistoryDrawer open={showHistory} onClose={() => setShowHistory(false)} messages={chat.messages} />

      {showSettings && (
        <div
          className="modal-overlay"
          onClick={(e) => e.target === e.currentTarget && closeSettings()}
        >
          <div className="modal-container" onClick={(e) => e.stopPropagation()}>
            <SettingsView onClose={closeSettings} onLogout={handleLogout} />
          </div>
        </div>
      )}
    </div>
  );
}
