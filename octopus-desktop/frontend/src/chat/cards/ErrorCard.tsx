export function ErrorCard({ message, retryable, onRetry }: { message: string; retryable: boolean; onRetry?: () => void }) {
  return (
    <div className="card card-error">
      <span>{message}</span>
      {retryable && onRetry && <button onClick={onRetry}>Coba lagi</button>}
    </div>
  );
}
