// Thin API client. Same-origin via the Vite proxy, so cookies just work.

export type Identity = {
  employee_no: string;
  name: string;
  role: string;
  email?: string;
};

export type TraceStep = {
  round: number;
  type: "tool" | "answer";
  tool?: string;
  args?: Record<string, unknown>;
  status?: string;
};

export type ChatResult = {
  answer: string;
  trace: TraceStep[];
  rounds: number;
};

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body.detail ?? body.reason ?? res.statusText;
  } catch {
    return res.statusText;
  }
}

export type PolicyChunk = {
  chunk_id: string;
  topic: string | null;
  subtopic: string | null;
  section: string | null;
  authority: string | null;
  jurisdiction: string[] | null;
  text: string;
  embedding: number[] | null;
};

export type PolicyDocument = {
  title: string;
  source_type: string;
  version: string;
  authority: string | null;
  effective_from: string | null;
  effective_to: string | null;
  source_url: string | null;
  chunk_count: number;
  chunks: PolicyChunk[];
};

export type AuditRow = {
  level: string;
  approver: string;
  decision: string;
  reason: string | null;
  decided_at: string;
};

export type RequestItem = {
  request_no: string;
  kind: "leave" | "flexible_work";
  summary: string;
  status: string;
  submitted_at: string | null;
  decided_at?: string | null;
  decision_reason?: string | null;
  statutory_due?: string | null;
  company_target?: string | null;
  employee_no?: string;
  employee_name?: string;
  audit: AuditRow[];
};

export const api = {
  async me(): Promise<Identity | null> {
    const res = await fetch("/auth/me", { credentials: "include" });
    if (res.status === 401) return null;
    if (!res.ok) throw new Error(await errorText(res));
    return res.json();
  },

  async login(email: string, password: string): Promise<Identity> {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error(await errorText(res));
    return res.json();
  },

  async policy(): Promise<PolicyDocument[]> {
    const res = await fetch("/policy", { credentials: "include" });
    if (res.status === 401) throw new Error("Session expired — please sign in again.");
    if (!res.ok) throw new Error(await errorText(res));
    return (await res.json()).documents;
  },

  async conversations(): Promise<Conversation[]> {
    const res = await fetch("/conversations", { credentials: "include" });
    if (res.status === 401) throw new Error("Session expired — please sign in again.");
    if (!res.ok) throw new Error(await errorText(res));
    return (await res.json()).conversations;
  },

  async conversationMessages(id: string): Promise<StoredMessage[]> {
    const res = await fetch(`/conversations/${id}/messages`, { credentials: "include" });
    if (res.status === 401) throw new Error("Session expired — please sign in again.");
    if (!res.ok) throw new Error(await errorText(res));
    return (await res.json()).messages;
  },

  async myRequests(): Promise<RequestItem[]> {
    const res = await fetch("/requests", { credentials: "include" });
    if (res.status === 401) throw new Error("Session expired — please sign in again.");
    if (!res.ok) throw new Error(await errorText(res));
    return (await res.json()).requests;
  },

  async pending(): Promise<RequestItem[]> {
    const res = await fetch("/pending", { credentials: "include" });
    if (res.status === 401) throw new Error("Session expired — please sign in again.");
    if (!res.ok) throw new Error(await errorText(res));
    return (await res.json()).pending;
  },

  async decide(
    requestNo: string,
    decision: "approved" | "rejected",
    reason?: string,
  ): Promise<{ status: string; new_status?: string; reason?: string; note?: string }> {
    const res = await fetch(`/requests/${requestNo}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ decision, reason: reason ?? null }),
    });
    if (res.status === 401) throw new Error("Session expired — please sign in again.");
    if (!res.ok) throw new Error(await errorText(res));
    return res.json();
  },

  async logout(): Promise<void> {
    await fetch("/auth/logout", { method: "POST", credentials: "include" });
  },

  async chat(message: string): Promise<ChatResult> {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ message }),
    });
    if (res.status === 401) throw new Error("Session expired — please sign in again.");
    if (!res.ok) throw new Error(await errorText(res));
    return res.json();
  },
};

// ── streaming: the agent's live progress (SSE) ──────────────────────────────

export type Conversation = {
  id: string;
  title: string | null;
  started_at: string;
  last_active_at: string;
};

export type StoredMessage = {
  role: "user" | "assistant";
  content: string;
  trace: TraceStep[] | null;
  created_at: string;
};

export type StreamEvent =
  | { type: "conversation"; conversation_id: string }
  | { type: "round"; round: number }
  | { type: "tool_request"; round: number; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; round: number; tool: string; status: string }
  | { type: "answer"; answer: string; rounds: number }
  | { type: "error"; reason: string };

export async function chatStream(
  message: string,
  onEvent: (ev: StreamEvent) => void,
  conversationId?: string | null,
): Promise<void> {
  const res = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
  });
  if (res.status === 401) throw new Error("Session expired — please sign in again.");
  if (!res.ok || !res.body) throw new Error(await errorText(res));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data: ")) continue;
      try {
        onEvent(JSON.parse(line.slice(6)) as StreamEvent);
      } catch {
        // malformed frame — skip, never break the stream over it
      }
    }
  }
}
