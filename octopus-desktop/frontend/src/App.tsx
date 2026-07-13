import { useEffect, useRef, useState } from "react";
import { ChatView } from "./chat/ChatView";
import { VoiceBar } from "./voice/VoiceBar";
import { speak } from "./voice/tts";
import { LoginView } from "./setup/LoginView";
import { SettingsView } from "./setup/SettingsView";
import "./style.css";

export default function App() {
  const [screen, setScreen] = useState<"loading" | "login" | "chat">("loading");
  const [showSettings, setShowSettings] = useState(false);
  const [jarvis, setJarvis] = useState(true);
  const submitRef = useRef<((text: string) => void) | null>(null);

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

  const handleTranscript = (text: string) => {
    if (jarvis) {
      submitRef.current?.(text); // auto-send
    } else {
      window.dispatchEvent(new CustomEvent("voice:draft", { detail: text }));
    }
  };

  const handleFinal = (text: string) => {
    if (jarvis) void speak(text).catch(() => {}); // TTS gagal tidak boleh ganggu chat
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
        <button className="settings-toggle-btn" onClick={() => setShowSettings(true)}>⚙️</button>
      </header>
      <main className="app-main">
        <ChatView
          onFinal={handleFinal}
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
