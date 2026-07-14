import { useEffect, useRef, useState } from "react";
import { ChatView } from "./chat/ChatView";
import { VoiceBar } from "./voice/VoiceBar";
import { speak } from "./voice/tts";
import { LoginView } from "./setup/LoginView";
import { SettingsView } from "./setup/SettingsView";
import { AiOrb } from "./orb/AiOrb";
import { deriveAiState } from "./orb/orbState";
import "./style.css";

export default function App() {
  const [screen, setScreen] = useState<"loading" | "login" | "chat">("loading");
  const [showSettings, setShowSettings] = useState(false);
  const [jarvis, setJarvis] = useState(true);
  const [pending, setPending] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [amplitude, setAmplitude] = useState(0);
  const submitRef = useRef<((text: string) => void) | null>(null);

  const aiState = deriveAiState(pending, isSpeaking);

  useEffect(() => {
    window.go.main.App.IsLoggedIn().then((loggedIn) => {
      if (loggedIn) {
        setScreen("chat");
      } else {
        setScreen("login");
      }
    });
  }, []);

  useEffect(() => {
    if (screen === "chat") {
      window.go.main.App.GetSettings().then((s) => setJarvis(Boolean(s.jarvis_mode)));
    }
  }, [screen]);

  useEffect(() => {
    if (screen !== "chat") return;
    const handleMove = (e: PointerEvent) => {
      const px = (e.clientX / window.innerWidth - 0.5) * 2;
      const py = (e.clientY / window.innerHeight - 0.5) * 2;
      document.documentElement.style.setProperty("--bg-parallax-x", `${(px * 6).toFixed(2)}px`);
      document.documentElement.style.setProperty("--bg-parallax-y", `${(py * 6).toFixed(2)}px`);
    };
    window.addEventListener("pointermove", handleMove);
    return () => window.removeEventListener("pointermove", handleMove);
  }, [screen]);

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
          <AiOrb state={aiState} amplitude={amplitude} />
        </div>
        <button className="settings-toggle-btn" onClick={() => setShowSettings(true)}>⚙️</button>
      </header>
      <main className="app-main">
        <ChatView
          onFinal={handleFinal}
          onPendingChange={setPending}
          registerSubmit={(fn) => (submitRef.current = fn)}
          inputExtra={
            <VoiceBar onTranscript={handleTranscript} jarvis={jarvis} onToggleJarvis={() => {
              const nextJarvis = !jarvis;
              setJarvis(nextJarvis);
              window.go.main.App.GetSettings().then(s => {
                window.go.main.App.SaveSettings({ ...s, jarvis_mode: nextJarvis });
              });
            }} />
          }
        />
      </main>
      {showSettings && (
        <div className="modal-overlay">
          <SettingsView onClose={() => setShowSettings(false)} onLogout={handleLogout} />
        </div>
      )}
    </div>
  );
}
