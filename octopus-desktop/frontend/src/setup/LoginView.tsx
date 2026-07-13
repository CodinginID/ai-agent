import { useEffect, useRef, useState } from "react";

export function LoginView({
  onPaired,
  pollIntervalMs = 2000,
}: {
  onPaired: () => void;
  pollIntervalMs?: number;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const timer = useRef<number | null>(null);

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
      setError(`Gateway tidak terjangkau: ${String(e)}`);
    }
  };

  return (
    <div className="login-view futuristic-card">
      <div className="corner-bracket top-left"></div>
      <div className="corner-bracket top-right"></div>
      <div className="corner-bracket bottom-left"></div>
      <div className="corner-bracket bottom-right"></div>
      <div className="glow-effect"></div>
      <h1>OCTOPUS //</h1>
      <p className="subtitle">[GATEWAY AUTHENTICATION PORTAL]</p>
      <button onClick={start} className="cyber-btn">INITIALIZE LOGIN SEQUENCE</button>
      {code && (
        <div className="pairing-box">
          <p className="pairing-status">AUTHENTICATING VIA BROWSER...</p>
          <p className="pairing-label">VERIFICATION CODE:</p>
          <div className="pairing-code">{code}</div>
        </div>
      )}
      {error && <p className="voice-error">{error}</p>}
    </div>
  );
}
