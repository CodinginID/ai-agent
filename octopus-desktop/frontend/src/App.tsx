import { useEffect, useRef, useState } from "react";
import { ChatView } from "./chat/ChatView";
import { VoiceBar } from "./voice/VoiceBar";
import { speak } from "./voice/tts";
import { LoginView } from "./setup/LoginView";
import { SettingsView } from "./setup/SettingsView";
import { AiOrb } from "./orb/AiOrb";
import { deriveAiState } from "./orb/orbState";
import "./style.css";

// Keyboard shortcut constants
const ESCAPE_KEY = "Escape";
const ENTER_KEY = "Enter";
const SPACE_KEY = " ";

export default function App() {
  const [screen, setScreen] = useState<"loading" | "login" | "chat">("loading");
  const [showSettings, setShowSettings] = useState(false);
  const [jarvis, setJarvis] = useState(true);
  const [vadSilenceMs, setVadSilenceMs] = useState(1200);
  const [pending, setPending] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [amplitude, setAmplitude] = useState(0);
  const submitRef = useRef<((text: string) => void) | null>(null);
  const chatInputRef = useRef<HTMLInputElement | null>(null);
  const voiceBarRef = useRef<HTMLDivElement | null>(null);

  const aiState = deriveAiState(pending, isSpeaking, isListening);

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Esc untuk tutup modal settings
      if (e.key === ESCAPE_KEY && showSettings) {
        setShowSettings(false);
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      // Ctrl+K atau Cmd+K untuk fokus ke chat input (jika di chat screen)
      if ((e.ctrlKey || e.metaKey) && e.key === "k" && screen === "chat") {
        e.preventDefault();
        chatInputRef.current?.focus();
      }
      // Space toggle Jarvis ketika voice bar focus
      if (e.key === SPACE_KEY && screen === "chat" && voiceBarRef.current?.contains(document.activeElement)) {
        e.preventDefault();
        e.stopPropagation();
        const nextJarvis = !jarvis;
        setJarvis(nextJarvis);
        window.go.main.App.GetSettings().then(s => {
          window.go.main.App.SaveSettings({ ...s, jarvis_mode: nextJarvis });
        });
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showSettings, screen, jarvis, voiceBarRef]);

  useEffect(() => {
    // Check if wails runtime is available
    if (!window.go || !window.go.main.App) {
      console.error("Wails runtime not loaded - this should not happen in production!");
      setScreen("chat"); // Fallback to chat view for development
      return;
    }

    window.go.main.App.IsLoggedIn().then((loggedIn) => {
      if (loggedIn) {
        setScreen("chat");
      } else {
        setScreen("login");
      }
    }).catch((err) => {
      console.error("Failed to check login status:", err);
      // Show error message or fallback
      setScreen("chat");
    });
  }, []);

  useEffect(() => {
    if (screen === "chat") {
      window.go.main.App.GetSettings().then((s) => {
        setJarvis(Boolean(s.jarvis_mode));
        const ms = Number((s as { vad_silence_ms?: number }).vad_silence_ms);
        if (Number.isFinite(ms) && ms > 0) setVadSilenceMs(ms);
      });
    }
  }, [screen]);

  useEffect(() => {
    if (screen !== "chat" || showSettings) return;
    const handleMove = (e: PointerEvent) => {
      const px = (e.clientX / window.innerWidth - 0.5) * 2;
      const py = (e.clientY / window.innerHeight - 0.5) * 2;
      document.documentElement.style.setProperty("--bg-parallax-x", `${(px * 6).toFixed(2)}px`);
      document.documentElement.style.setProperty("--bg-parallax-y", `${(py * 6).toFixed(2)}px`);
    };
    window.addEventListener("pointermove", handleMove);
    return () => window.removeEventListener("pointermove", handleMove);
  }, [screen, showSettings]);

  const handleTranscript = (text: string) => {
    if (jarvis) {
      submitRef.current?.(text); // auto-send
    } else {
      window.dispatchEvent(new CustomEvent("voice:draft", { detail: text }));
    }
  };

  const handleFinal = (text: string) => {
    if (!jarvis) return;
    setIsSpeaking(true);
    void speak(text, (level) => setAmplitude(level))
      .catch(() => {}) // TTS gagal tidak boleh ganggu chat
      .finally(() => {
        setIsSpeaking(false);
        setAmplitude(0);
      });
  };

  const handleLogout = async () => {
    await window.go.main.App.Logout();
    setShowSettings(false);
    setScreen("login");
  };

  if (screen === "loading") {
    return <div className="loading-screen">Memuat...</div>;
  }

  if (screen === "login") {
    return <LoginView onPaired={() => setScreen("chat")} />;
  }

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Octopus Desktop</h1>
        <div className="app-header-orb">
          <AiOrb state={aiState} amplitude={amplitude} paused={showSettings} />
        </div>
        <button className="settings-toggle-btn" onClick={() => setShowSettings(true)}>⚙️</button>
      </header>
      <main className="app-main">
        <ChatView
          ref={chatInputRef}
          onFinal={handleFinal}
          onPendingChange={setPending}
          registerSubmit={(fn) => (submitRef.current = fn)}
          inputExtra={
            <div ref={voiceBarRef}>
              <VoiceBar
                onTranscript={handleTranscript}
                vadSilenceMs={vadSilenceMs}
                jarvis={jarvis}
                onToggleJarvis={() => {
                  const nextJarvis = !jarvis;
                  setJarvis(nextJarvis);
                  window.go.main.App.GetSettings().then(s => {
                    window.go.main.App.SaveSettings({ ...s, jarvis_mode: nextJarvis });
                  });
                }}
                onListeningChange={setIsListening}
              />
            </div>
          }
        />
      </main>
      {showSettings && (
        <div className="modal-overlay" onClick={(e) => {
          // Hanya tutup kalau klik area gelap (bukan kontennya)
          if (e.target === e.currentTarget) setShowSettings(false);
        }}>
          <div className="modal-container" onClick={(e) => e.stopPropagation()}>
            <SettingsView onClose={() => setShowSettings(false)} onLogout={handleLogout} />
          </div>
        </div>
      )}
    </div>
  );
}
