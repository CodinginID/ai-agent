export function computeRmsAmplitude(data: Uint8Array): number {
  let sumSquares = 0;
  for (let i = 0; i < data.length; i++) {
    const norm = (data[i] - 128) / 128;
    sumSquares += norm * norm;
  }
  return Math.min(1, Math.sqrt(sumSquares / data.length) * 4);
}

export async function speak(text: string, onAmplitude?: (level: number) => void): Promise<void> {
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

  try {
    await new Promise<void>((resolve, reject) => {
      audio.addEventListener("ended", () => resolve(), { once: true });
      audio.addEventListener("error", () => reject(new Error("Playback gagal")), { once: true });
      audio.play().catch(reject);
    });
  } finally {
    if (rafId !== null) cancelAnimationFrame(rafId);
    if (audioCtx) await audioCtx.close();
    URL.revokeObjectURL(url);
  }
}
