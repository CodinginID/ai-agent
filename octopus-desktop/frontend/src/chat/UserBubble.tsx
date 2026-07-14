import { usePointerTilt } from "../hooks/usePointerTilt";

export function UserBubble({ text }: { text: string }) {
  const ref = usePointerTilt<HTMLDivElement>();
  return (
    <div ref={ref} className="msg-user tilt-surface">
      {text}
    </div>
  );
}
