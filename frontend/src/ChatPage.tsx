import { useEffect, useRef, useState } from "react";
import {
  api,
  chatStream,
  type Conversation,
  type Identity,
  type StreamEvent,
  type TraceStep,
} from "./api";

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
const LAST_CONVERSATION_KEY = "wr_last_conversation";

export default function ChatPage({
  identity,
  onLogout,
  onShowPolicy,
  onShowRequests,
  onShowApprovals,
}: {
  identity: Identity;
  onLogout: () => void;
  onShowPolicy: () => void;
  onShowRequests: () => void;
  onShowApprovals: () => void;
}) {
  const greeting: Message = {
    id: nextId++,
    role: "assistant",
    text: `Hi ${identity.name.split(" ")[0]} — ask me about your leave, or request a flexible-working arrangement. I can look things up and file requests, but humans decide.`,
  };
  const [messages, setMessages] = useState<Message[]>([greeting]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<Live | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  // on load: refresh the conversation list, restore the last conversation
  useEffect(() => {
    api.conversations().then(setConversations).catch(() => {});
    const last = localStorage.getItem(LAST_CONVERSATION_KEY);
    if (!last) return;
    api
      .conversationMessages(last)
      .then((stored) => {
        if (stored.length === 0) return;
        setConversationId(last);
        setMessages([
          greeting,
          ...stored.map((m) =>
            m.role === "user"
              ? { id: nextId++, role: "user" as const, text: m.content }
              : { id: nextId++, role: "assistant" as const, text: m.content,
                  trace: m.trace ?? undefined },
          ),
        ]);
      })
      .catch(() => localStorage.removeItem(LAST_CONVERSATION_KEY));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function switchConversation(id: string) {
    if (busy) return;
    if (!id) {
      newChat();
      return;
    }
    const stored = await api.conversationMessages(id);
    setConversationId(id);
    localStorage.setItem(LAST_CONVERSATION_KEY, id);
    setMessages([
      greeting,
      ...stored.map((m) =>
        m.role === "user"
          ? { id: nextId++, role: "user" as const, text: m.content }
          : { id: nextId++, role: "assistant" as const, text: m.content,
              trace: m.trace ?? undefined },
      ),
    ]);
  }

  function newChat() {
    setConversationId(null);
    localStorage.removeItem(LAST_CONVERSATION_KEY);
    setMessages([{ ...greeting, id: nextId++ }]);
    setError(null);
  }

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
        case "conversation":
          setConversationId(ev.conversation_id);
          localStorage.setItem(LAST_CONVERSATION_KEY, ev.conversation_id);
          break;
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
      await chatStream(message, onEvent, conversationId);
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
      api.conversations().then(setConversations).catch(() => {});
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
          <select
            className="conv-select"
            value={conversationId ?? ""}
            disabled={busy}
            onChange={(e) => switchConversation(e.target.value)}
            title="Your conversations"
          >
            <option value="">＋ New chat</option>
            {conversations.map((c) => (
              <option key={c.id} value={c.id}>
                {(c.title ?? "conversation").slice(0, 40)}
              </option>
            ))}
          </select>
          <button className="ghost" onClick={onShowRequests}>
            My requests
          </button>
          {identity.role !== "employee" && (
            <button className="ghost" onClick={onShowApprovals}>
              Approvals
            </button>
          )}
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
