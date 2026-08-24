export interface VadParams {
  threshold: number; // RMS di atas ini dianggap "ada suara"
  silenceMs: number; // lama hening yang mengakhiri ujaran
  minSpeechMs: number; // minimal rentang bicara sebelum silence bisa mengakhiri
}

export const DEFAULT_VAD: VadParams = {
  threshold: 0.02,
  silenceMs: 1200,
  minSpeechMs: 300,
};

// Detektor aktivitas suara berbasis energi, murni tanpa Web Audio.
// Waktu di-inject lewat `nowMs` supaya deterministik & teruji.
export class VadDetector {
  private speechStartMs: number | null = null;
  private lastLoudMs: number | null = null;
  private done = false;

  constructor(private readonly params: VadParams) {}

  feed(rms: number, nowMs: number): boolean {
    if (this.done) return false;

    if (rms >= this.params.threshold) {
      if (this.speechStartMs === null) this.speechStartMs = nowMs;
      this.lastLoudMs = nowMs;
      return false;
    }

    if (this.speechStartMs === null || this.lastLoudMs === null) return false;

    const spanMs = this.lastLoudMs - this.speechStartMs;
    const silentForMs = nowMs - this.lastLoudMs;
    if (spanMs >= this.params.minSpeechMs && silentForMs >= this.params.silenceMs) {
      this.done = true;
      return true;
    }
    return false;
  }

  reset(): void {
    this.speechStartMs = null;
    this.lastLoudMs = null;
    this.done = false;
  }
}
