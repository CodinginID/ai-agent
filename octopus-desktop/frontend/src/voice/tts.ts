export function computeRmsAmplitude(data: Uint8Array): number {
  let sumSquares = 0;
  for (let i = 0; i < data.length; i++) {
    const norm = (data[i] - 128) / 128;
    sumSquares += norm * norm;
  }
  return Math.min(1, Math.sqrt(sumSquares / data.length) * 4);
}

interface ActivePlayback {
  audio: HTMLAudioElement;
  cleanup: () => void;
  resolve: () => void;
}

let active: ActivePlayback | null = null;

// Menghentikan TTS yang sedang berjalan (barge-in). Aman & idempotent
// dipanggil saat tidak ada playback. Promise speak() yang bersangkutan
// resolve normal — bukan reject — agar tidak memunculkan error di chat.
export function cancelSpeech(): void {
  const p = active;
  if (!p) return;
  active = null;
  try {
    p.audio.pause();
  } catch {
    // pause tidak kritis; playback dianggap berhenti
  }
  p.cleanup();
  p.resolve();
}

export async function speak(text: string, onAmplitude?: (level: number) => void): Promise<void> {
  cancelSpeech(); // hentikan ucapan sebelumnya sebelum mulai yang baru
  const b64 = await window.go.main.App.Speak(text);
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  const audio = new Audio(url);

  let audioCtx: AudioContext | null = null;
  let rafId: number | null = null;

  if (onAmplitude) {
    audioCtx = new AudioContext();
    const source = audioCtx.createMediaElementSource(audio);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    analyser.connect(audioCtx.destination);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      onAmplitude(computeRmsAmplitude(data));
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
  }

  let cleaned = false;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    if (rafId !== null) cancelAnimationFrame(rafId);
    if (audioCtx) void audioCtx.close();
    URL.revokeObjectURL(url);
  };

  await new Promise<void>((resolve, reject) => {
    active = { audio, cleanup, resolve };
    const clearActive = () => {
      if (active?.audio === audio) active = null;
    };
    audio.addEventListener(
      "ended",
      () => {
        cleanup();
        clearActive();
        resolve();
      },
      { once: true },
    );
    audio.addEventListener(
      "error",
      () => {
        cleanup();
        clearActive();
        reject(new Error("Playback gagal"));
      },
      { once: true },
    );
    audio.play().catch((err) => {
      cleanup();
      clearActive();
      reject(err);
    });
  });
}
