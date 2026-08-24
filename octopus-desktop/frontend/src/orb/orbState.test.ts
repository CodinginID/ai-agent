import { describe, expect, it } from "vitest";
import { computeOrbUniforms, deriveAiState, ORB_COLORS } from "./orbState";

describe("ORB_COLORS (palet gelap orb-centric)", () => {
  it("idle cyan, listening hijau, thinking & speaking amber", () => {
    expect(ORB_COLORS.idle).toBe("#38e1ff");
    expect(ORB_COLORS.listening).toBe("#3ddc97");
    expect(ORB_COLORS.thinking).toBe("#ffb454");
    expect(ORB_COLORS.speaking).toBe("#ffb454");
  });
});

describe("computeOrbUniforms", () => {
  it("idle: breathing berosilasi, distortion tetap kecil", () => {
    const u0 = computeOrbUniforms("idle", 0, 0);
    expect(u0.breathScale).toBeCloseTo(0, 5);
    expect(u0.distortion).toBeCloseTo(0.08, 5);
    expect(u0.colorMix).toBe(0);

    const uQuarter = computeOrbUniforms("idle", 0, Math.PI / 2 / 1.2);
    expect(uQuarter.breathScale).toBeCloseTo(0.04, 5);
  });

  it("thinking: distortion tinggi dan colorMix penuh ke amber", () => {
    const u = computeOrbUniforms("thinking", 0, 5);
    expect(u.distortion).toBeCloseTo(0.35, 5);
    expect(u.colorMix).toBe(1);
    expect(u.breathScale).toBe(0);
  });

  it("speaking: distortion mengikuti amplitude, di-clamp ke [0,1]", () => {
    expect(computeOrbUniforms("speaking", 0, 1).distortion).toBe(0);
    expect(computeOrbUniforms("speaking", 0.5, 1).distortion).toBeCloseTo(0.3, 5);
    expect(computeOrbUniforms("speaking", 5, 1).distortion).toBeCloseTo(0.6, 5);
    expect(computeOrbUniforms("speaking", -5, 1).distortion).toBe(0);
  });
});

describe("deriveAiState", () => {
  it("speaking menang atas pending", () => {
    expect(deriveAiState(true, true, false)).toBe("speaking");
  });
  it("pending tanpa speaking -> thinking", () => {
    expect(deriveAiState(true, false, false)).toBe("thinking");
  });
  it("tidak pending & tidak speaking -> idle", () => {
    expect(deriveAiState(false, false, false)).toBe("idle");
  });
  it("listening menang atas semua", () => {
    expect(deriveAiState(true, true, true)).toBe("listening");
  });
});
