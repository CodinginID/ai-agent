import * as THREE from "three";

// Orbit particle shader - light office theme
// Uses lighter, more visible colors for white/light backgrounds
export const ORBIT_VERTEX_SHADER = `
  attribute float aId;

  uniform float uTime;
  uniform float uAmplitude;

  varying vec3 vWorldPos;
  varying float vSpeed;
  varying float vRadius;
  varying float vPhase;

  void main() {
    vSpeed = 0.3 + mod(aId * 0.618033988749895, 1.5);
    vRadius = 0.7 + mod(aId * 0.381966011250105, 0.8);
    vPhase = mod(aId * 2.399963229728653, 6.283185307179586);

    float angle = vPhase + uTime * vSpeed;
    float incl = sin(aId * 0.7) * 1.4;
    float r = vRadius;

    vec3 offset = vec3(
      r * cos(angle) * cos(incl),
      r * sin(angle) * sin(incl) + sin(uTime * 0.5) * uAmplitude * 0.3,
      r * cos(angle) * sin(incl)
    );

    vWorldPos = position + offset;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(vWorldPos, 1.0);
    gl_PointSize = max(1.0, (3.0 + uAmplitude * 2.0) * (3.5 / -modelViewMatrix[3].z));
  }
`;

export const ORBIT_FRAGMENT_SHADER = `
  uniform vec3 uColorA;
  uniform vec3 uColorB;
  uniform vec3 uColorC;
  uniform float uColorMix;

  varying vec3 vWorldPos;
  varying float vSpeed;
  varying float vRadius;
  varying float vPhase;

  void main() {
    vec2 coord = gl_PointCoord - 0.5;
    float d = length(coord);
    if (d > 0.5) discard;

    float glow = 1.0 - smoothstep(0.0, 0.5, d);
    glow = pow(glow, 1.8);

    vec3 base = mix(uColorA, uColorB, 0.5 + 0.5 * sin(vPhase + length(vWorldPos) * 0.5));
    vec3 final = mix(base, uColorC, uColorMix);

    float alpha = glow * 0.9;
    gl_FragColor = vec4(final * (0.6 + glow * 0.7), alpha);
  }
`;

export function createOrbitMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uColorA: { value: new THREE.Color("#5b9bd5") },
      uColorB: { value: new THREE.Color("#6bc99a") },
      uColorC: { value: new THREE.Color("#f6ad55") },
      uColorMix: { value: 0 },
      uAmplitude: { value: 0 },
    },
    vertexShader: ORBIT_VERTEX_SHADER,
    fragmentShader: ORBIT_FRAGMENT_SHADER,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
}
