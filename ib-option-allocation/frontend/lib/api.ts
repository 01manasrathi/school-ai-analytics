// Thin fetch wrapper. All calls go to /api/* which next.config.js proxies to FastAPI (http://127.0.0.1:8000).

const TOKEN_KEY = "ib_token";
const USER_KEY = "ib_user";

export type User = { username: string; role: "ADMIN" | "READONLY" };

export class ApiError extends Error {
  constructor(public status: number, public detail: any) {
    super(typeof detail === "string" ? detail : detail?.message || JSON.stringify(detail));
  }
}

export const auth = {
  token: () => (typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY)),
  user: (): User | null => {
    if (typeof window === "undefined") return null;
    const u = localStorage.getItem(USER_KEY);
    return u ? JSON.parse(u) : null;
  },
  save: (token: string, user: User) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

export async function api<T = any>(path: string, opts: { method?: string; body?: any; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = auth.token();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  if (res.status === 401 && typeof window !== "undefined" && !path.includes("/auth/login")) {
    auth.clear();
    window.location.href = "/login";
  }
  const text = await res.text();
  const data = text ? (() => { try { return JSON.parse(text); } catch { return text; } })() : null;
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data);
  return data as T;
}

export async function downloadCsv(path: string, filename: string) {
  const res = await fetch(path + (path.includes("?") ? "&" : "?") + "format=csv", {
    headers: { Authorization: `Bearer ${auth.token()}` },
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function errorText(e: any): string {
  if (e instanceof ApiError) {
    const d = e.detail;
    if (d?.errors) return `${d.message}:\n` + d.errors.map((x: any) => `• ${x.student_id ? x.student_id + ": " : ""}${x.message}`).join("\n");
    if (d?.feasibility) return `${d.message}\n` + d.feasibility.reasons.map((r: string) => `• ${r}`).join("\n");
    if (Array.isArray(d)) return d.map((x: any) => x.msg).join("; ");
    return e.message;
  }
  return String(e);
}
