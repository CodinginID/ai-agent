import { describe, expect, it } from "vitest";
import { DEFAULT_VAD, VadDetector } from "./vad";

const LOUD = 0.1; // di atas threshold default 0.02
const QUIET = 0.0;

/** Umpankan urutan frame; kembalikan ms saat feed pertama return true, atau null. */
function runFrames(det: VadDetector, frames: { rms: number; t: number }[]): number | null {
  for (const f of frames) {
    if (det.feed(f.rms, f.t)) return f.t;
  }
  return null;
}

describe("VadDetector", () => {
  it("tidak pernah speech-end bila hening terus (belum mulai bicara)", () => {
    const det = new VadDetector(DEFAULT_VAD);
    const frames = Array.from({ length: 50 }, (_, i) => ({ rms: QUIET, t: i * 100 }));
    expect(runFrames(det, frames)).toBeNull();
  });

  it("speech-end tepat sekali setelah bicara lalu diam >= silenceMs", () => {
    const det = new VadDetector(DEFAULT_VAD);
    const frames: { rms: number; t: number }[] = [];
    for (let t = 0; t <= 500; t += 100) frames.push({ rms: LOUD, t }); // 500ms bicara
    for (let t = 600; t <= 2200; t += 100) frames.push({ rms: QUIET, t }); // diam
    const firedAt = runFrames(det, frames);
    expect(firedAt).not.toBeNull();
    // terakhir loud di t=500; silence 1200ms tercapai di t=1700
    expect(firedAt).toBe(1700);
  });

  it("hanya memicu sekali, feed berikutnya false sampai reset", () => {
    const det = new VadDetector(DEFAULT_VAD);
    for (let t = 0; t <= 500; t += 100) det.feed(LOUD, t);
    expect(det.feed(QUIET, 1700)).toBe(true);
    expect(det.feed(QUIET, 1800)).toBe(false);
    expect(det.feed(QUIET, 5000)).toBe(false);
    det.reset();
    expect(det.feed(QUIET, 5100)).toBe(false); // hening lagi, belum bicara
  });

  it("guard minSpeech: spike sesaat lalu diam tidak memicu", () => {
    const det = new VadDetector(DEFAULT_VAD);
    const frames = [
      { rms: LOUD, t: 0 }, // satu spike, span 0 < minSpeechMs
      ...Array.from({ length: 40 }, (_, i) => ({ rms: QUIET, t: 100 + i * 100 })),
    ];
    expect(runFrames(det, frames)).toBeNull();
  });

  it("jeda singkat (< silenceMs) di tengah bicara tidak memicu", () => {
    const det = new VadDetector(DEFAULT_VAD);
    const frames = [
      { rms: LOUD, t: 0 },
      { rms: LOUD, t: 100 },
      { rms: QUIET, t: 200 }, // jeda 500ms
      { rms: QUIET, t: 400 },
      { rms: QUIET, t: 600 },
      { rms: LOUD, t: 700 }, // lanjut bicara
      { rms: LOUD, t: 800 },
    ];
    expect(runFrames(det, frames)).toBeNull();
  });

  it("DEFAULT_VAD punya nilai wajar", () => {
    expect(DEFAULT_VAD.silenceMs).toBe(1200);
    expect(DEFAULT_VAD.threshold).toBeGreaterThan(0);
    expect(DEFAULT_VAD.minSpeechMs).toBeGreaterThan(0);
  });
});
