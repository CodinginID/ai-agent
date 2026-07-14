import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computeRmsAmplitude, speak } from "./tts";

describe("computeRmsAmplitude", () => {
  it("mengembalikan 0 untuk data hening (semua 128)", () => {
    expect(computeRmsAmplitude(new Uint8Array(8).fill(128))).toBe(0);
  });

  it("meng-clamp hasil ke maksimum 1", () => {
    expect(computeRmsAmplitude(new Uint8Array(8).fill(255))).toBe(1);
  });
});

class FakeAudio extends EventTarget {
  src: string;
  constructor(src: string) {
    super();
    this.src = src;
  }
  play = vi.fn(() => {
    queueMicrotask(() => this.dispatchEvent(new Event("ended")));
    return Promise.resolve();
  });
}

class FakeAudioContextCtor {
  static instances: FakeAudioContextCtor[] = [];
  destination = {};
  createMediaElementSource = vi.fn(() => ({ connect: vi.fn() }));
  createAnalyser = vi.fn(() => ({
    fftSize: 0,
    frequencyBinCount: 32,
    connect: vi.fn(),
    getByteTimeDomainData: (arr: Uint8Array) => arr.fill(128),
  }));
  close = vi.fn().mockResolvedValue(undefined);
  constructor() {
    FakeAudioContextCtor.instances.push(this);
  }
}

beforeEach(() => {
  FakeAudioContextCtor.instances = [];
  (window as any).go = { main: { App: { Speak: vi.fn().mockResolvedValue(btoa("data")) } } };
  vi.stubGlobal("Audio", FakeAudio);
  vi.stubGlobal("AudioContext", FakeAudioContextCtor);
  URL.createObjectURL = vi.fn(() => "blob:fake");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("speak", () => {
  it("resolve setelah event ended dan revoke object URL", async () => {
    await expect(speak("halo")).resolves.toBeUndefined();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake");
  });

  it("tidak membuat AudioContext bila onAmplitude tidak diberikan", async () => {
    await speak("halo");
    expect(FakeAudioContextCtor.instances).toHaveLength(0);
  });

  it("membuat AudioContext dan menutupnya saat onAmplitude diberikan", async () => {
    await speak("halo", () => {});
    expect(FakeAudioContextCtor.instances).toHaveLength(1);
    expect(FakeAudioContextCtor.instances[0].close).toHaveBeenCalled();
  });
});
