import { create } from "zustand";
import { persist } from "zustand/middleware";

type ThemeMode = "auto" | "light" | "dark";

interface ThemeState {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
}

function applyTheme(theme: ThemeMode) {
  if (theme === "auto") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: "auto" as ThemeMode,
      setTheme: (theme: ThemeMode) => {
        applyTheme(theme);
        set({ theme });
      },
    }),
    {
      name: "fojin-theme",
    },
  ),
);

// Apply theme on load
const stored = localStorage.getItem("fojin-theme");
if (stored) {
  try {
    const parsed = JSON.parse(stored);
    if (parsed?.state?.theme) {
      applyTheme(parsed.state.theme);
    }
  } catch {
    // ignore
  }
}
