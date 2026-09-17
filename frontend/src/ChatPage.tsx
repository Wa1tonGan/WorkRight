import { useRef, useState } from "react";
import { api, type ChatResult, type Identity, type TraceStep } from "./api";

type Message =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; text: string; trace?: TraceStep[] };

const SUGGESTIONS = [
  "How many annual leave days do I have left?",
  "Please book my annual leave for 24 and 25 December 2026.",
  "I'd like to work from home three days a week starting 1 December 2026.",
  "Can I carry unused leave into next year?",
];

let nextId = 1;

export default function ChatPage({
  identity,
  onLogout,
}: {
  identity: Identity;
  onLogout: () => void;
}) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: nextId++,
      role: "assistant",
      text: `Hi ${identity.name.split(" ")[0]} — ask me about your leave, or request a flexible-working arrangement. I can look things up and file requests, but humans decide.`,
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setError(null);
    setMessages((m) => [...m, { id: nextId++, role: "user", text: message }]);
    setBusy(true);
    try {
      const result: ChatResult = await api.chat(message);
      setMessages((m) => [
        ...m,
        { id: nextId++, role: "assistant", text: result.answer, trace: result.trace },
      ]);
    } catch (err) {
      const reason = err instanceof Error ? err.message : "Something went wrong";
      setError(reason);
      if (reason.includes("Session expired")) onLogout();
    } finally {
      setBusy(false);
      requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));
    }
  }

  return (
    <div className="chat-shell">
      <header className="chat-header">
        <div>
          <div className="brand">WorkRight</div>
          <div className="who">
            {identity.name} · <span className="role">{identity.role}</span> ·{" "}
            {identity.employee_no}
          </div>
        </div>
        <button className="ghost" onClick={onLogout}>
          Sign out
        </button>
      </header>

      <main className="chat-main">
        {messages.map((m) => {
          const tools =
            m.role === "assistant"
              ? (m.trace ?? []).filter((t) => t.type === "tool")
              : [];
          return (
            <div key={m.id} className={`bubble ${m.role}`}>
              <div className="text">{m.text}</div>
              {tools.length > 0 && (
                <details className="trace">
                  <summary>
                    what happened ({tools.length} tool call
                    {tools.length === 1 ? "" : "s"})
                  </summary>
                  <ol>
                    {tools.map((t, i) => (
                      <li key={i}>
                        <code>{t.tool}</code>
                        {t.args && Object.keys(t.args).length > 0 && (
                          <span className="args">({JSON.stringify(t.args)})</span>
                        )}{" "}
                        → <b className={t.status}>{t.status}</b>
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>
          );
        })}
        {busy && <div className="bubble assistant typing">Thinking… (the model runs on this Mac — a few seconds)</div>}
        {error && <div className="error inline">{error}</div>}
        <div ref={bottomRef} />
      </main>

      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="chip" disabled={busy} onClick={() => send(s)}>
            {s}
          </button>
        ))}
      </div>

      <footer className="chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder={busy ? "Please wait…" : "Ask about leave or flexible working…"}
          disabled={busy}
        />
        <button onClick={() => send(input)} disabled={busy || !input.trim()}>
          Send
        </button>
      </footer>
    </div>
  );
}
