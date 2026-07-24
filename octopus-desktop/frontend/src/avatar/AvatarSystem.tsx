import { useEffect, useState } from "react";
import { useAvatarState } from "./hooks/useAvatarState";
import { Avatar } from "./Avatar";
import type { WorkerAvatar } from "./types";

// Singleton amplitude untuk avatar — TTS speaking akan update nilai ini.
// Hanya satu "speaker" utama (orb AI) di interface.
let globalAmplitude = 0;
let globalAmplitudeListeners: Set<(amp: number) => void> = new Set();

export function useGlobalAmplitude() {
  const [amp, setAmp] = useState(globalAmplitude);

  useEffect(() => {
    globalAmplitudeListeners.add(setAmp);
    return () => {
      globalAmplitudeListeners.delete(setAmp);
    };
  }, []);

  useEffect(() => {
    globalAmplitude = amp;
    for (const l of globalAmplitudeListeners) l(amp);
  }, [amp]);
}

// Register amplitude updaters — App.tsx memanggil useGlobalAmplitude()
// untuk subscribe ke perubahan amplitude dari TTS speak().
export function registerAmplitudeListener(cb: (amp: number) => void) {
  globalAmplitudeListeners.add(cb);
  return () => { globalAmplitudeListeners.delete(cb); };
}

export function setGlobalAmplitude(value: number) {
  globalAmplitude = value;
  for (const l of globalAmplitudeListeners) l(value);
}

export function AvatarSystem() {
  const workers = useAvatarState();
  const [amplitude, setAmplitude] = useState(0);

  useEffect(() => {
    const unsub = registerAmplitudeListener(setAmplitude);
    return unsub;
  }, []);

  return (
    <div className="avatar-system" aria-label="Worker avatars">
      {workers.map((w: WorkerAvatar) => (
        <Avatar
          key={w.id}
          workerId={w.id}
          workerName={w.name}
          workerType={w.type}
          workerColor={w.color}
          state={w.state}
          task={w.task}
          amplitude={amplitude}
        />
      ))}
    </div>
  );
}
