import { describe, expect, it } from "vitest";
import { lerp, makeBlobs, mixColor, PLASMA_PALETTE, PLASMA_STATES } from "./plasma";

describe("PLASMA_STATES (parameter mockup #78)", () => {
  it("memuat tint, kecepatan, dan radius persis nilai mockup", () => {
    expect(PLASMA_STATES.idle).toMatchObject({ tint: [90, 200, 255], speed: 0.22, radius: 92 });
    expect(PLASMA_STATES.listening).toMatchObject({ tint: [70, 230, 160], radius: 100 });
    expect(PLASMA_STATES.thinking).toMatchObject({ tint: [255, 185, 90], speed: 1.3 });
    expect(PLASMA_STATES.speaking).toMatchObject({ tint: [120, 235, 255], radius: 104 });
  });

  it("setiap state punya labelKey i18n", () => {
    for (const s of Object.values(PLASMA_STATES)) {
      expect(s.labelKey).toMatch(/^orb_state_/);
    }
  });
});

describe("helper plasma", () => {
  it("lerp menginterpolasi linear", () => {
    expect(lerp(0, 10, 0.5)).toBe(5);
    expect(lerp(2, 2, 0.9)).toBe(2);
  });

  it("mixColor mencampur per kanal", () => {
    expect(mixColor([0, 0, 0], [100, 200, 50], 0.5)).toEqual([50, 100, 25]);
  });

  it("makeBlobs menghasilkan satu blob per warna palet dengan orbit bervariasi", () => {
    const blobs = makeBlobs();
    expect(blobs).toHaveLength(PLASMA_PALETTE.length);
    expect(new Set(blobs.map((b) => b.orbit)).size).toBeGreaterThan(1);
  });
});
