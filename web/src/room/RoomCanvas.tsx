import { useRef } from "react";
import { useRoomEngine } from "./useRoomEngine";

export function RoomCanvas({ hideHint }: { hideHint?: boolean } = {}): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useRoomEngine(canvasRef);

  return (
    <div className="relative h-full w-full overflow-hidden bg-bg">
      <canvas
        ref={canvasRef}
        className="block h-full w-full touch-none"
        aria-label="Ruang Octopus — office virtual agen AI"
      />
      {!hideHint && (
      <div className="pointer-events-none absolute bottom-3 left-3.5 rounded-md border border-line bg-[var(--c-namebg)] px-2.5 py-1.5 text-[11.5px] text-ink-faint backdrop-blur">
        Klik/ketuk avatar untuk detail · tugas berisiko butuh persetujuanmu
      </div>
      )}
    </div>
  );
}
