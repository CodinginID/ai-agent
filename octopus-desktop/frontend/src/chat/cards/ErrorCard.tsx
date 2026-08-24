import { Tilt } from "../../components/Tilt";
import { useI18n } from "../../i18n/useI18n";

export function ErrorCard({ message, retryable, onRetry }: { message: string; retryable: boolean; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <Tilt className="card card-error">
      <span>{message}</span>
      {retryable && onRetry && <button onClick={onRetry}>{t("card_retry")}</button>}
    </Tilt>
  );
}
