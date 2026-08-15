import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
}

interface AuthState {
  token: string | null;
  user: UserProfile | null;
  setAuth: (token: string, user: UserProfile) => void;
  logout: () => void;
}

/**
 * Set when the 401 interceptor logs someone out, i.e. their session died on its
 * own rather than at their request. It has to live outside the auth store
 * because that store is exactly what gets cleared: by the time any UI can react,
 * `user` is already null and "expired" is indistinguishable from "never logged
 * in". sessionStorage (not localStorage) so it dies with the tab and cannot
 * outlive the situation it describes.
 */
export const SESSION_EXPIRED_KEY = "fojin.auth.expired";

// sessionStorage is not reactive, so components read it through
// useSyncExternalStore — the supported way to subscribe React to an external
// mutable source. The earlier shape (useState + an effect that re-read on every
// [user, quota] change) piggybacked on unrelated re-renders and tripped
// react-hooks/set-state-in-effect; this fires exactly when the value changes.
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((l) => l());
}

export function subscribeSessionExpired(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => { listeners.delete(onChange); };
}

export function markSessionExpired(): void {
  try { sessionStorage.setItem(SESSION_EXPIRED_KEY, "1"); } catch { /* ignore */ }
  notify();
}

export function clearSessionExpired(): void {
  try { sessionStorage.removeItem(SESSION_EXPIRED_KEY); } catch { /* ignore */ }
  notify();
}

/** getSnapshot for useSyncExternalStore — a primitive, so Object.is is enough. */
export function sessionExpired(): boolean {
  try { return sessionStorage.getItem(SESSION_EXPIRED_KEY) === "1"; } catch { return false; }
}

/** getServerSnapshot — the prerender worker has no session to have lost. */
export function sessionExpiredServer(): boolean {
  return false;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      // A fresh sign-in ends the expired state — otherwise the notice would
      // survive the very act that fixes it.
      setAuth: (token, user) => { clearSessionExpired(); set({ token, user }); },
      // Deliberate sign-out is not an expiry; only the 401 path marks it.
      logout: () => { clearSessionExpired(); set({ token: null, user: null }); },
    }),
    { name: "fojin-auth" },
  ),
);
