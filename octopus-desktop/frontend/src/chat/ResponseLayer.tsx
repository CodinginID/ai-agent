export interface ResponseLayerProps {
  text: string;
  streaming?: boolean;
}

// Teks jawaban ephemeral di bawah orb. Kosong = tidak merender apa pun.
export function ResponseLayer({ text, streaming = false }: ResponseLayerProps) {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return (
    <div
      className={`response-layer ${streaming ? "streaming" : ""}`}
      role="status"
      aria-live="polite"
      key={trimmed.length}
    >
      <p>{trimmed}</p>
    </div>
  );
}
