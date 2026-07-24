import { useEffect, useState } from "react";
import { useThemeStore, resolveTheme } from "../stores/themeStore";

const MQ = "(prefers-color-scheme: dark)";

export function useEffectiveTheme(): "light" | "dark" {
  const mode = useThemeStore((s) => s.mode);
  const [prefersDark, setPrefersDark] = useState(() => window.matchMedia(MQ).matches);
  useEffect(() => {
    const mql = window.matchMedia(MQ);
    const onChange = (e: MediaQueryListEvent) => setPrefersDark(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return resolveTheme(mode, prefersDark);
}

export function useApplyTheme(): "light" | "dark" {
  const effective = useEffectiveTheme();
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", effective);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", effective === "dark" ? "#3a3126" : "#8b2500");
  }, [effective]);
  return effective;
}
