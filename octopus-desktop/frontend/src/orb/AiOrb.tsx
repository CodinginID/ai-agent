import { Canvas, useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";
import "./orbMaterial";
import { computeOrbUniforms, type OrbState } from "./orbState";

function OrbMesh({ state, amplitude }: { state: OrbState; amplitude: number }) {
  const materialRef = useRef<any>(null);
  const meshRef = useRef<THREE.Mesh>(null);
  const elapsed = useRef(0);

  useFrame((_, delta) => {
    elapsed.current += delta;
    const u = computeOrbUniforms(state, amplitude, elapsed.current);
    if (meshRef.current) {
      meshRef.current.rotation.y += u.rotationSpeed * delta;
      meshRef.current.scale.setScalar(1 + u.breathScale);
    }
    if (materialRef.current) {
      materialRef.current.uTime = elapsed.current;
      materialRef.current.uDistortion = u.distortion;
      materialRef.current.uColorMix = u.colorMix;
    }
  });

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1, 4]} />
      <orbMaterial ref={materialRef} transparent />
    </mesh>
  );
}

export function AiOrb({ state, amplitude = 0 }: { state: OrbState; amplitude?: number }) {
  return (
    <Canvas camera={{ position: [0, 0, 2.5], fov: 40 }} gl={{ alpha: true, antialias: true }}>
      <ambientLight intensity={0.6} />
      <pointLight position={[2, 2, 2]} intensity={1.2} />
      <OrbMesh state={state} amplitude={amplitude} />
    </Canvas>
  );
}
