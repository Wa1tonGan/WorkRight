import { useRef, useState } from "react";
import { chatStream, type Identity, type StreamEvent, type TraceStep } from "./api";

type Message =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; text: string; trace?: TraceStep[] };

type LiveStep = { tool: string; args?: Record<string, unknown>; status?: string };
type Live = { round: number; steps: LiveStep[] };

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
  onShowPolicy,
}: {
  identity: Identity;
  onLogout: () => void;
  onShowPolicy: () => void;
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
  const [live, setLive] = useState<Live | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setError(null);
    setMessages((m) => [...m, { id: nextId++, role: "user", text: message }]);
    setBusy(true);
    setLive({ round: 1, steps: [] });

    const toolSteps: TraceStep[] = [];
    let answerText = "";
    let streamError: string | null = null;

    const onEvent = (ev: StreamEvent) => {
      switch (ev.type) {
        case "round":
          setLive((l) => (l ? { ...l, round: ev.round } : l));
          break;
        case "tool_request":
          toolSteps.push({ round: ev.round, type: "tool", tool: ev.tool, args: ev.args });
          setLive((l) =>
            l ? { ...l, steps: [...l.steps, { tool: ev.tool, args: ev.args }] } : l,
          );
          break;
        case "tool_result": {
          const step = [...toolSteps].reverse().find((s) => s.tool === ev.tool && !s.status);
          if (step) step.status = ev.status;
          setLive((l) => {
            if (!l) return l;
            const steps = [...l.steps];
            for (let i = steps.length - 1; i >= 0; i--) {
              if (steps[i].tool === ev.tool && !steps[i].status) {
                steps[i] = { ...steps[i], status: ev.status };
                break;
              }
            }
            return { ...l, steps };
          });
          break;
        }
        case "answer":
          answerText = ev.answer;
          break;
        case "error":
          streamError = ev.reason;
          break;
      }
    };

    try {
      await chatStream(message, onEvent);
      if (streamError) throw new Error(streamError);
      if (!answerText) throw new Error("The agent did not produce an answer — try again.");
      setMessages((m) => [
        ...m,
        { id: nextId++, role: "assistant", text: answerText, trace: toolSteps },
      ]);
    } catch (err) {
      const reason = err instanceof Error ? err.message : "Something went wrong";
      setError(reason);
      if (reason.includes("Session expired")) onLogout();
    } finally {
      setBusy(false);
      setLive(null);
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
        <div className="header-actions">
          <button className="ghost" onClick={onShowPolicy}>
            Policies
          </button>
          <button className="ghost" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>

      <main className="chat-main">
        {messages.map((m) => {
          const tools =
            m.role === "assistant" ? (m.trace ?? []).filter((t) => t.type === "tool") : [];
          return (
            <div key={m.id} className={`bubble ${m.role}`}>
              <div className="text">{m.text}</div>
              {tools.length > 0 && (
                <details className="trace" open>
                  <summary>
                    agent activity ({tools.length} tool call
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

        {live && (
          <div className="bubble assistant live">
            <div className="live-title">
              <span className="pulse" />
              thinking — round {live.round}
            </div>
            {live.steps.length > 0 && (
              <ol className="live-steps">
                {live.steps.map((s, i) => (
                  <li key={i}>
                    <code>{s.tool}</code>
                    {s.args && Object.keys(s.args).length > 0 && (
                      <span className="args">({JSON.stringify(s.args)})</span>
                    )}{" "}
                    →{" "}
                    {s.status ? (
                      <b className={s.status}>{s.status}</b>
                    ) : (
                      <span className="running">running…</span>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}

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
