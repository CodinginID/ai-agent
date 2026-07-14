import { shaderMaterial } from "@react-three/drei";
import { extend } from "@react-three/fiber";
import * as THREE from "three";

const OrbMaterialImpl = shaderMaterial(
  {
    uTime: 0,
    uDistortion: 0.08,
    uColorA: new THREE.Color("#3b82f6"),
    uColorB: new THREE.Color("#10b981"),
    uColorC: new THREE.Color("#f59e0b"),
    uColorMix: 0,
  },
  `
    uniform float uTime;
    uniform float uDistortion;
    varying vec3 vNormal;
    varying vec3 vPosition;

    float noise(vec3 p) {
      return sin(p.x * 3.0 + uTime) * sin(p.y * 3.0 + uTime) * sin(p.z * 3.0 + uTime);
    }

    void main() {
      vNormal = normalize(normalMatrix * normal);
      vec3 displaced = position + normal * noise(position) * uDistortion;
      vPosition = displaced;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
    }
  `,
  `
    uniform vec3 uColorA;
    uniform vec3 uColorB;
    uniform vec3 uColorC;
    uniform float uColorMix;
    varying vec3 vNormal;
    varying vec3 vPosition;

    void main() {
      float fresnel = pow(1.0 - abs(dot(normalize(vNormal), vec3(0.0, 0.0, 1.0))), 2.0);
      vec3 base = mix(uColorA, uColorB, 0.5 + 0.5 * sin(vPosition.y * 2.0));
      vec3 withGlow = mix(base, uColorC, uColorMix);
      gl_FragColor = vec4(withGlow * (0.4 + fresnel * 1.2), 0.85);
    }
  `,
);

extend({ orbMaterial: OrbMaterialImpl });

declare module "@react-three/fiber" {
  interface ThreeElements {
    orbMaterial: any;
  }
}

export { OrbMaterialImpl };
