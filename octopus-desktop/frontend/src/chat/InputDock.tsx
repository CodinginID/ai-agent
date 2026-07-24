import { forwardRef, useEffect, useState, type ReactNode } from "react";

export interface InputDockProps {
  onSubmit: (text: string) => void;
  voiceSlot?: ReactNode;
}

// Dock input bawah: teks (Enter kirim) + slot VoiceBar (mic fallback).
// Mendengarkan "voice:draft" untuk mengisi input dari transkrip non-jarvis.
export const InputDock = forwardRef<HTMLInputElement, InputDockProps>(
  ({ onSubmit, voiceSlot }, ref) => {
    const [draft, setDraft] = useState("");

    useEffect(() => {
      const handler = (e: Event) => setDraft((e as CustomEvent<string>).detail);
      window.addEventListener("voice:draft", handler);
      return () => window.removeEventListener("voice:draft", handler);
    }, []);

    const send = () => {
      onSubmit(draft);
      setDraft("");
    };

    return (
      <div className="input-dock">
        {voiceSlot}
        <input
          ref={ref}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ketik perintah… atau klik orb untuk bicara"
          aria-label="Tulis pesan"
        />
        <button className="input-dock-send" onClick={send} aria-label="Kirim pesan">
          Kirim
        </button>
      </div>
    );
  },
);
