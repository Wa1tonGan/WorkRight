import { useEffect, useState } from "react";
import { api, type RequestItem } from "./api";
import { AuditList, statusClass } from "./RequestCard";

export default function MyRequestsPage({ onBack }: { onBack: () => void }) {
  const [items, setItems] = useState<RequestItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.myRequests().then(setItems).catch((e) =>
      setError(e instanceof Error ? e.message : "failed to load"));
  }, []);

  return (
    <div className="chat-shell">
      <header className="chat-header">
        <div>
          <div className="brand">My Requests</div>
          <div className="who">everything you've asked for, and what happened to it</div>
        </div>
        <button className="ghost" onClick={onBack}>← Back to chat</button>
      </header>
      <main className="chat-main policy-main">
        {error && <div className="error inline">{error}</div>}
        {!items && !error && <div className="bubble assistant typing">loading…</div>}
        {items?.length === 0 && (
          <div className="bubble assistant">No requests yet — ask in the chat to book leave or arrange flexible working.</div>
        )}
        {items?.map((r) => (
          <section key={r.request_no} className="req-card">
            <div className="req-head">
              <code>{r.request_no}</code>
              <span className={`badge status ${statusClass(r.status)}`}>{r.status.replace("_", " ")}</span>
              <span className="badge">{r.kind === "leave" ? "leave" : "flexible work"}</span>
            </div>
            <div className="req-summary">{r.summary}</div>
            <div className="req-meta">
              submitted {r.submitted_at?.slice(0, 16).replace("T", " ")}
              {r.decided_at ? ` · decided ${r.decided_at.slice(0, 16).replace("T", " ")}` : ""}
              {r.statutory_due ? ` · statutory due ${r.statutory_due.slice(0, 10)}` : ""}
            </div>
            <details className="audit" open={r.audit.length > 0}>
              <summary>audit trail ({r.audit.length})</summary>
              <AuditList audit={r.audit} />
              {r.decision_reason && <div className="audit-empty">reason: {r.decision_reason}</div>}
            </details>
          </section>
        ))}
      </main>
    </div>
  );
}
