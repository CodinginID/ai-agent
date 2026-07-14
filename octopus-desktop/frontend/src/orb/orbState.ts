export type OrbState = "idle" | "thinking" | "speaking";

export interface OrbUniformParams {
  rotationSpeed: number;
  breathScale: number;
  distortion: number;
  colorMix: number;
}

const BASE: Record<OrbState, { rotationSpeed: number; distortion: number; colorMix: number }> = {
  idle: { rotationSpeed: 0.15, distortion: 0.08, colorMix: 0 },
  thinking: { rotationSpeed: 0.6, distortion: 0.35, colorMix: 1 },
  speaking: { rotationSpeed: 0.3, distortion: 0, colorMix: 0.15 },
};

export function computeOrbUniforms(
  state: OrbState,
  amplitude: number,
  elapsedSeconds: number,
): OrbUniformParams {
  const base = BASE[state];
  const breathScale = state === "idle" ? 0.04 * Math.sin(elapsedSeconds * 1.2) : 0;
  const distortion = state === "speaking" ? Math.min(1, Math.max(0, amplitude)) * 0.6 : base.distortion;
  return {
    rotationSpeed: base.rotationSpeed,
    breathScale,
    distortion,
    colorMix: base.colorMix,
  };
}

export function deriveAiState(pending: boolean, speaking: boolean): OrbState {
  if (speaking) return "speaking";
  if (pending) return "thinking";
  return "idle";
}
