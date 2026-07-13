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
    <div className="login-view">
      <h1>Octopus</h1>
      <p>Login untuk terhubung ke gateway Octopus kamu.</p>
      <button onClick={start}>Login dengan Google</button>
      {code && (
        <p>
          Browser terbuka — pastikan kodenya sama: <strong>{code}</strong>
        </p>
      )}
      {error && <p className="voice-error">{error}</p>}
    </div>
  );
}
