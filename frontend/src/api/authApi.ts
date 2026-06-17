import type { AuthResponse, User } from "../types/user";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export async function getMe(token: string): Promise<User> {
  return request<User>("/auth/me", { headers: { Authorization: `Bearer ${token}` } });
}

export async function listUsers(token: string): Promise<User[]> {
  return request<User[]>("/users", { headers: { Authorization: `Bearer ${token}` } });
}
