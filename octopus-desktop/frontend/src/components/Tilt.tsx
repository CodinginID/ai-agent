import type { ReactNode } from "react";
import { usePointerTilt } from "../hooks/usePointerTilt";

export function Tilt({ className, children }: { className: string; children: ReactNode }) {
  const ref = usePointerTilt<HTMLDivElement>();
  return (
    <div ref={ref} className={`tilt-surface ${className}`}>
      {children}
    </div>
  );
}
