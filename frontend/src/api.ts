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
