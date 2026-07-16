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
