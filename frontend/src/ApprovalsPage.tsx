import { useEffect, useState } from "react";
import { api, type RequestItem } from "./api";
import { AuditList, statusClass } from "./RequestCard";

export default function ApprovalsPage({ onBack }: { onBack: () => void }) {
  const [items, setItems] = useState<RequestItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyNo, setBusyNo] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  async function refresh() {
    setItems(await api.pending());
  }

  useEffect(() => {
    refresh().catch((e) => setError(e instanceof Error ? e.message : "failed to load"));
  }, []);

  async function act(requestNo: string, decision: "approved" | "rejected", why?: string) {
    setBusyNo(requestNo);
    setNotice(null);
    setError(null);
    try {
      const result = await api.decide(requestNo, decision, why);
      setNotice(
        result.status === "advanced"
          ? `${requestNo}: manager stage recorded — now awaiting HR`
          : result.status === "decided"
            ? `${requestNo}: ${decision} recorded with full audit trail`
            : `${requestNo}: ${result.status} — ${result.reason ?? ""}`,
      );
      setRejecting(null);
      setReason("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "action failed");
    } finally {
      setBusyNo(null);
    }
  }

  return (
    <div className="chat-shell">
      <header className="chat-header">
        <div>
          <div className="brand">Approvals</div>
          <div className="who">requests awaiting YOUR decision — the same rules as in chat</div>
        </div>
        <button className="ghost" onClick={onBack}>← Back to chat</button>
      </header>
      <main className="chat-main policy-main">
        {error && <div className="error inline">{error}</div>}
        {notice && <div className="notice">{notice}</div>}
        {!items && !error && <div className="bubble assistant typing">loading…</div>}
        {items?.length === 0 && (
          <div className="bubble assistant">Nothing needs your decision right now.</div>
        )}
        {items?.map((r) => (
          <section key={r.request_no} className="req-card">
            <div className="req-head">
              <code>{r.request_no}</code>
              <span className={`badge status ${statusClass(r.status)}`}>{r.status.replace("_", " ")}</span>
              <span className="badge">{r.employee_name} · {r.employee_no}</span>
            </div>
            <div className="req-summary">{r.summary}</div>
            <div className="req-meta">
              submitted {r.submitted_at?.slice(0, 16).replace("T", " ")}
            </div>
            {r.audit.length > 0 && (
              <details className="audit">
                <summary>previous stage ({r.audit.length})</summary>
                <AuditList audit={r.audit} />
              </details>
            )}

            {rejecting === r.request_no ? (
              <div className="reject-box">
                <input
                  autoFocus
                  placeholder="Reason for rejection (required — it is recorded)"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <button
                  className="danger"
                  disabled={!reason.trim() || busyNo === r.request_no}
                  onClick={() => act(r.request_no, "rejected", reason)}
                >
                  Confirm rejection
                </button>
                <button className="ghost" onClick={() => { setRejecting(null); setReason(""); }}>
                  Cancel
                </button>
              </div>
            ) : (
              <div className="req-actions">
                <button disabled={busyNo === r.request_no} onClick={() => act(r.request_no, "approved")}>
                  Approve
                </button>
                <button
                  className="ghost"
                  disabled={busyNo === r.request_no}
                  onClick={() => setRejecting(r.request_no)}
                >
                  Reject…
                </button>
              </div>
            )}
          </section>
        ))}
      </main>
    </div>
  );
}
