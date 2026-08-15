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

export function markSessionExpired(): void {
  try { sessionStorage.setItem(SESSION_EXPIRED_KEY, "1"); } catch { /* ignore */ }
}

export function clearSessionExpired(): void {
  try { sessionStorage.removeItem(SESSION_EXPIRED_KEY); } catch { /* ignore */ }
}

export function sessionExpired(): boolean {
  try { return sessionStorage.getItem(SESSION_EXPIRED_KEY) === "1"; } catch { return false; }
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
