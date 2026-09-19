import type { RequestItem } from "./api";

export function statusClass(status: string): string {
  if (["approved", "created", "decided"].includes(status)) return "ok";
  if (["pending_manager", "pending_hr", "draft"].includes(status)) return "wait";
  if (["rejected", "cancelled", "escalated"].includes(status)) return "bad";
  return "info";
}

export function AuditList({ audit }: { audit: RequestItem["audit"] }) {
  if (!audit || audit.length === 0) {
    return <div className="audit-empty">no decisions recorded yet</div>;
  }
  return (
    <ol className="audit-list">
      {audit.map((a, i) => (
        <li key={i}>
          <b className={a.decision === "approved" ? "ok" : "bad"}>{a.decision}</b>{" "}
          at <b>{a.level}</b> stage by <b>{a.approver}</b>
          {a.reason ? ` — "${a.reason}"` : ""}
          <span className="when"> · {a.decided_at?.slice(0, 16).replace("T", " ")}</span>
        </li>
      ))}
    </ol>
  );
}
