import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useRef, useMemo } from "react";
import * as THREE from "three";
import { createOrbitMaterial, ORBIT_FRAGMENT_SHADER, ORBIT_VERTEX_SHADER } from "./orbMaterial";
import { computeOrbUniforms, ORB_COLORS, type OrbState } from "./orbState";

// Generate orbit particle data
function generateOrbitParticles(count: number) {
  const positions = new Float32Array(count * 3);
  const aIds = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    positions[i * 3] = 0;
    positions[i * 3 + 1] = 0;
    positions[i * 3 + 2] = 0;
    aIds[i] = i;
  }

  return { positions, aIds };
}

function OrbitParticles() {
  const pointsRef = useRef<THREE.Points>(null);
  const matRef = useRef<THREE.ShaderMaterial | null>(null);
  const elapsed = useRef(0);
  const particleData = useMemo(() => generateOrbitParticles(180), []);

  useFrame((_, delta: number) => {
    elapsed.current += delta;
    const mat = matRef.current;
    if (mat) {
      mat.uniforms.uTime.value = elapsed.current;
    }
    if (pointsRef.current) {
      pointsRef.current.rotation.y += 0.15 * delta;
      pointsRef.current.rotation.x = Math.sin(elapsed.current * 0.3) * 0.1;
    }
  });

  useEffect(() => {
    const mat = createOrbitMaterial();
    matRef.current = mat;

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(particleData.positions, 3));
    geometry.setAttribute("aId", new THREE.BufferAttribute(particleData.aIds, 1));

    if (pointsRef.current) {
      (pointsRef.current as THREE.Points).geometry = geometry;
      (pointsRef.current as THREE.Points).material = mat;
    }

    return () => {
      mat.dispose();
      geometry.dispose();
      matRef.current = null;
    };
  }, []);

  return (
    <points ref={pointsRef}>
    </points>
  );
}

function CoreSphere({ amplitude, color }: { amplitude: number; color: string }) {
  const sphereRef = useRef<THREE.Mesh>(null);

  useFrame((_, delta: number) => {
    if (sphereRef.current) {
      const pulse = 1 + amplitude * 0.3;
      sphereRef.current.scale.setScalar(pulse);
    }
  });

  return (
    <mesh ref={sphereRef}>
      <sphereGeometry args={[0.25, 16, 16]} />
      <meshBasicMaterial color={color} transparent opacity={0.65} />
    </mesh>
  );
}

export function AiOrb({
  state,
  amplitude = 0,
  paused = false,
}: {
  state: OrbState;
  amplitude?: number;
  paused?: boolean;
}) {
  return (
    <Canvas
      frameloop={paused ? "never" : "always"}
      camera={{ position: [0, 0, 3.5], fov: 45 }}
      gl={{ alpha: true, antialias: true }}
    >
      <ambientLight intensity={0.3} />
      <pointLight position={[2, 2, 3]} intensity={1.2} />
      <pointLight position={[-2, -1, 2]} intensity={0.6} color={ORB_COLORS[state]} />
      <OrbitParticles />
      <CoreSphere amplitude={amplitude} color={ORB_COLORS[state]} />
    </Canvas>
  );
}
