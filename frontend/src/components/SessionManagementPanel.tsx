import { useEffect, useState } from "react";

import { listActiveSessions, revokeActiveSession } from "../api/authApi";
import type { ActiveSession } from "../types/user";


interface SessionManagementPanelProps {
  csrfToken: string;
}


function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString();
}


export function SessionManagementPanel({ csrfToken }: SessionManagementPanelProps) {
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!csrfToken) return;
    setLoading(true);
    setError(null);
    listActiveSessions(csrfToken)
      .then(setSessions)
      .catch((apiError: Error) => setError(apiError.message))
      .finally(() => setLoading(false));
  }, [csrfToken]);

  async function revoke(session: ActiveSession): Promise<void> {
    if (session.current_session || !window.confirm(`Revoke the active session for ${session.user_email}?`)) return;
    setLoading(true);
    setError(null);
    try {
      await revokeActiveSession(csrfToken, session.id);
      setSessions((current) => current.filter((item) => item.id !== session.id));
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not revoke session");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="border-b border-slate-200 p-3 text-xs">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold uppercase tracking-wide text-slate-500">Active sessions</h2>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">{sessions.length}</span>
      </div>
      <p className="mt-1 text-[10px] leading-4 text-slate-500">No token, IP address, or user-agent data is exposed.</p>
      {loading && sessions.length === 0 ? <p className="mt-2 text-slate-500">Loading sessions…</p> : null}
      {error ? <p className="mt-2 text-red-700">{error}</p> : null}
      <div className="mt-2 space-y-2">
        {sessions.map((session) => (
          <div className="rounded border border-slate-200 bg-slate-50 p-2" key={session.id}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-medium text-slate-800">{session.user_email}</p>
                <p className="mt-1 text-[10px] text-slate-500">Last active {formatTimestamp(session.last_seen_at)}</p>
                <p className="text-[10px] text-slate-500">Idle limit {formatTimestamp(session.idle_expires_at)}</p>
                <p className="text-[10px] text-slate-500">Absolute limit {formatTimestamp(session.absolute_expires_at)}</p>
              </div>
              {session.current_session ? (
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800">Current</span>
              ) : (
                <button
                  className="rounded border border-red-200 px-1.5 py-0.5 text-[10px] text-red-700 hover:bg-red-50 disabled:opacity-50"
                  disabled={loading}
                  onClick={() => void revoke(session)}
                  type="button"
                >
                  Revoke
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
