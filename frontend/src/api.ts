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

export type StreamEvent =
  | { type: "round"; round: number }
  | { type: "tool_request"; round: number; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; round: number; tool: string; status: string }
  | { type: "answer"; answer: string; rounds: number }
  | { type: "error"; reason: string };

export async function chatStream(
  message: string,
  onEvent: (ev: StreamEvent) => void,
): Promise<void> {
  const res = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ message }),
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
