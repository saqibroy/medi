export type UserRole = "admin" | "annotator" | "reviewer";

export interface User {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  expires_at: string;
  csrf_token: string;
  user: User;
}

export interface CsrfResponse {
  csrf_token: string;
}

export interface ActiveSession {
  id: string;
  user_id: string;
  user_email: string;
  created_at: string;
  last_seen_at: string;
  idle_expires_at: string;
  absolute_expires_at: string;
  current_session: boolean;
}
