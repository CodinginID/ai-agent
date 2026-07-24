import { useEffect, useRef, useState } from "react";
import { usePointerTilt } from "../hooks/usePointerTilt";
import { useI18n } from "../i18n/useI18n";

export function LoginView({
  onPaired,
  pollIntervalMs = 2000,
}: {
  onPaired: () => void;
  pollIntervalMs?: number;
}) {
  const { t } = useI18n();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const timer = useRef<number | null>(null);
  const tiltRef = usePointerTilt<HTMLDivElement>();

  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current); }, []);

  const start = async () => {
    try {
      const res = await window.go.main.App.StartLogin();
      setCode(String(res.code));
      timer.current = window.setInterval(async () => {
        try {
          const status = await window.go.main.App.PollLogin(String(res.code));
          if (status === "paired") {
            if (timer.current) window.clearInterval(timer.current);
            onPaired();
          }
        } catch (e) {
          if (timer.current) window.clearInterval(timer.current);
          setError(String(e));
        }
      }, pollIntervalMs);
    } catch (e) {
      setError(t("login_gateway_unreachable", { err: String(e) }));
    }
  };

  return (
    <div ref={tiltRef} className="login-view card tilt-surface">
      <h1>{t("app_name")}</h1>
      <p className="subtitle">{t("login_connect")}</p>
      <button onClick={start} className="card-btn">{t("login_connect_btn")}</button>
      {code && (
        <div className="pairing-box">
          <p className="pairing-status">{t("login_authenticating")}</p>
          <p className="pairing-label">{t("login_verification_code")}</p>
          <div className="pairing-code">{code}</div>
        </div>
      )}
      {error && <p className="voice-error">{error}</p>}
    </div>
  );
}
