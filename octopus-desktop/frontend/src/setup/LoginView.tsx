import { useEffect, useRef, useState } from "react";
import { usePointerTilt } from "../hooks/usePointerTilt";

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
      setError(`Gateway tidak terjangkau: ${String(e)}`);
    }
  };

  return (
    <div ref={tiltRef} className="login-view card tilt-surface">
      <h1>Octopus</h1>
      <p className="subtitle">Connect your gateway</p>
      <button onClick={start} className="card-btn">Connect</button>
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
