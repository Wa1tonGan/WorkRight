import { useState } from "react";
import { api, type Identity } from "./api";

// One shared demo password for all fictional employees (seeded server-side).
const DEMO_PASSWORD = "workright123";

const CAST = [
  { email: "weijie.lim@example.my", label: "Wei Jie · Employee" },
  { email: "siti.yusof@example.my", label: "Siti · Manager" },
  { email: "ravi.kumar@example.my", label: "Ravi · HR" },
  { email: "jelin.ujin@example.my", label: "Jelin · Sabah (escalation)" },
  { email: "danial.rahim@example.my", label: "Danial · New joiner" },
];

export default function LoginPage({ onLogin }: { onLogin: (id: Identity) => void }) {
  const [email, setEmail] = useState(CAST[0].email);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await api.login(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <h1>WorkRight</h1>
        <p className="subtitle">HR assistant for leave &amp; flexible working</p>

        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {error && <div className="error">{error}</div>}

        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <div className="cast">
          <div className="cast-title">Demo cast — click to switch, password pre-filled</div>
          {CAST.map((c) => (
            <button
              type="button"
              key={c.email}
              className={"cast-chip" + (c.email === email ? " active" : "")}
              onClick={() => setEmail(c.email)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}
