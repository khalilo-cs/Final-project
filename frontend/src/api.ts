// Thin client for the backend services (all behind /svc/<name>, see vite.config.ts).

export type Role = "admin" | "faculty" | "student";

export interface User {
  id: string;
  username: string;
  full_name: string;
  email: string;
  role: Role;
  student_id: string | null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const TOKEN_KEY = "aipe.tokens";

interface Tokens {
  access_token: string;
  refresh_token: string;
}

export function loadTokens(): Tokens | null {
  const raw = sessionStorage.getItem(TOKEN_KEY);
  return raw ? (JSON.parse(raw) as Tokens) : null;
}

export function saveTokens(tokens: Tokens | null) {
  if (tokens) sessionStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
  else sessionStorage.removeItem(TOKEN_KEY);
}

async function refresh(): Promise<boolean> {
  const tokens = loadTokens();
  if (!tokens) return false;
  const response = await fetch("/svc/auth/api/v1/auth/refresh-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!response.ok) {
    saveTokens(null);
    return false;
  }
  saveTokens(await response.json());
  return true;
}

function detail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const value = (body as { detail: unknown }).detail;
    if (typeof value === "string") return value;
    if (Array.isArray(value)) return value.map((v) => v.msg ?? String(v)).join("، ");
  }
  return fallback;
}

export async function request<T>(
  service: "auth" | "projects" | "viva",
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  const tokens = loadTokens();
  if (tokens) headers.set("Authorization", `Bearer ${tokens.access_token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/svc/${service}${path}`, { ...init, headers });
  if (response.status === 401 && retry && (await refresh())) {
    return request<T>(service, path, init, false);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, detail(body, `خطأ ${response.status}`));
  }
  if (response.status === 204) return undefined as T;
  const type = response.headers.get("content-type") ?? "";
  return (type.includes("json") ? response.json() : response.blob()) as Promise<T>;
}

export const get = <T,>(service: "auth" | "projects" | "viva", path: string) =>
  request<T>(service, path);

export const post = <T,>(
  service: "auth" | "projects" | "viva",
  path: string,
  body?: unknown,
) =>
  request<T>(service, path, {
    method: "POST",
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  });

export const put = <T,>(service: "auth" | "projects" | "viva", path: string, body: unknown) =>
  request<T>(service, path, { method: "PUT", body: JSON.stringify(body) });

export async function download(service: "projects" | "viva", path: string, filename: string) {
  const blob = await request<Blob>(service, path);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
