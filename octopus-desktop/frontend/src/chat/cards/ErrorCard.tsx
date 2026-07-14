import { Tilt } from "../../components/Tilt";

export function ErrorCard({ message, retryable, onRetry }: { message: string; retryable: boolean; onRetry?: () => void }) {
  return (
    <Tilt className="card card-error">
      <span>{message}</span>
      {retryable && onRetry && <button onClick={onRetry}>Coba lagi</button>}
    </Tilt>
  );
}
