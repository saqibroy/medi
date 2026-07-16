import type { AuthResponse, CsrfResponse, User } from "../types/user";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function getCsrfToken(): Promise<string> {
  return (await request<CsrfResponse>("/auth/csrf")).csrf_token;
}

export async function login(email: string, password: string, csrfToken: string): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", { method: "POST", headers: { "X-CSRF-Token": csrfToken }, body: JSON.stringify({ email, password }) });
}

export async function getMe(): Promise<User> {
  return request<User>("/auth/me");
}

export async function logout(csrfToken: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
}

export async function listUsers(csrfToken: string): Promise<User[]> {
  return request<User[]>("/users", { headers: { "X-CSRF-Token": csrfToken } });
}
