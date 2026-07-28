import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeMode = "light" | "dark" | "system";

/** Pure resolver. MUST stay identical to the inline script in index.html. */
export function resolveTheme(mode: ThemeMode, prefersDark: boolean): "light" | "dark" {
  if (mode === "light" || mode === "dark") return mode;
  return prefersDark ? "dark" : "light";
}

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: "system",
      setMode: (mode) => set({ mode }),
    }),
    { name: "fojin-theme" },
  ),
);
