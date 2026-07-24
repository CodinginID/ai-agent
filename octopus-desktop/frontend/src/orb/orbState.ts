export type OrbState = "idle" | "thinking" | "speaking" | "listening";

export interface OrbUniformParams {
  rotationSpeed: number;
  breathScale: number;
  distortion: number;
  colorMix: number;
}

export interface OrbColors {
  idle: string;
  thinking: string;
  speaking: string;
  listening: string;
}

const COLORS: OrbColors = {
  idle: "#38e1ff", // cyan tenang
  thinking: "#ffb454", // amber
  speaking: "#ffb454", // amber, denyut mengikuti amplitudo TTS
  listening: "#3ddc97", // hijau
};

const BASE: Record<OrbState, { rotationSpeed: number; distortion: number; colorMix: number }> = {
  idle: { rotationSpeed: 0.15, distortion: 0.08, colorMix: 0 },
  thinking: { rotationSpeed: 0.6, distortion: 0.35, colorMix: 1 },
  speaking: { rotationSpeed: 0.3, distortion: 0, colorMix: 0.15 },
  listening: { rotationSpeed: 0.2, distortion: 0.05, colorMix: 0.1 },
};

export const ORB_COLORS = COLORS;

export function computeOrbUniforms(
  state: OrbState,
  amplitude: number,
  elapsedSeconds: number,
): OrbUniformParams {
  const base = BASE[state];
  const breathScale =
    state === "idle"
      ? 0.04 * Math.sin(elapsedSeconds * 1.2)
      : state === "listening"
        ? 0.03 * Math.sin(elapsedSeconds * 0.8)
        : 0;
  const distortion =
    state === "speaking" ? Math.min(1, Math.max(0, amplitude)) * 0.6 : base.distortion;
  return {
    rotationSpeed: base.rotationSpeed,
    breathScale,
    distortion,
    colorMix: base.colorMix,
  };
}

export function deriveAiState(
  pending: boolean,
  speaking: boolean,
  isListening: boolean,
): OrbState {
  if (isListening) return "listening";
  if (speaking) return "speaking";
  if (pending) return "thinking";
  return "idle";
}
