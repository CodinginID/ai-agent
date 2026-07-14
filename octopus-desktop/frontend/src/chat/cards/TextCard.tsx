import { Tilt } from "../../components/Tilt";

export function TextCard({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <Tilt className="card card-text">
      <div style={{ whiteSpace: "pre-wrap" }}>{text}</div>
      {streaming && <span className="cursor">▌</span>}
    </Tilt>
  );
}
