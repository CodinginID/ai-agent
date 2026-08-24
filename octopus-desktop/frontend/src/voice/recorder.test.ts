import { describe, expect, it } from "vitest";
import { computeFrameRms, encodeWAV } from "./recorder";

describe("computeFrameRms", () => {
  it("mengembalikan 0 untuk frame senyap", () => {
    expect(computeFrameRms(new Float32Array(1024))).toBe(0);
  });

  it("frame keras menghasilkan RMS di atas threshold VAD default", () => {
    const frame = new Float32Array(1024).fill(0.5);
    expect(computeFrameRms(frame)).toBeGreaterThan(0.02);
  });

  it("frame kosong tidak NaN", () => {
    expect(computeFrameRms(new Float32Array(0))).toBe(0);
  });
});

describe("encodeWAV", () => {
  it("menghasilkan header RIFF/WAVE dengan ukuran benar", () => {
    const samples = new Float32Array(16000); // 1 detik silence @16kHz
    const buf = encodeWAV(samples, 16000);
    const view = new DataView(buf);
    const tag = (off: number) =>
      String.fromCharCode(view.getUint8(off), view.getUint8(off + 1), view.getUint8(off + 2), view.getUint8(off + 3));
    expect(tag(0)).toBe("RIFF");
    expect(tag(8)).toBe("WAVE");
    expect(view.getUint32(24, true)).toBe(16000); // sample rate
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(buf.byteLength).toBe(44 + samples.length * 2);
  });

  it("meng-clamp sample di luar [-1,1]", () => {
    const buf = encodeWAV(new Float32Array([2.0, -2.0]), 16000);
    const view = new DataView(buf);
    expect(view.getInt16(44, true)).toBe(32767);
    expect(view.getInt16(46, true)).toBe(-32768);
  });
});
