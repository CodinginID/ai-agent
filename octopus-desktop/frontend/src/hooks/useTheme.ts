import { useEffect, useState, useCallback } from "react";

const THEME_KEY = "octopus-theme";
const SUPPORTED_THEMES = ["auto", "light", "dark"] as const;
export type ThemeOption = (typeof SUPPORTED_THEMES)[number];

function resolveSystemTheme(): "light" | "dark" {
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return "light";
}

function getInitialTheme(): ThemeOption {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored && SUPPORTED_THEMES.includes(stored as ThemeOption)) {
      return stored as ThemeOption;
    }
  } catch {
    // localStorage unavailable
  }
  return "auto";
}

function applyTheme(theme: ThemeOption): void {
  const resolved = theme === "auto" ? resolveSystemTheme() : theme;
  document.documentElement.dataset.theme = resolved;
}

export function useTheme(): {
  theme: ThemeOption;
  resolved: "light" | "dark";
  setTheme: (t: ThemeOption) => void;
  toggle: () => void;
} {
  const [theme, setThemeState] = useState<ThemeOption>(getInitialTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Listen for system theme changes when in auto mode
  useEffect(() => {
    if (theme !== "auto") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("auto");
    if (mql.addEventListener) {
      mql.addEventListener("change", handler);
    }
    return () => {
      if (mql.removeEventListener) {
        mql.removeEventListener("change", handler);
      }
    };
  }, [theme]);

  const setTheme = useCallback((t: ThemeOption) => {
    setThemeState(t);
    try {
      localStorage.setItem(THEME_KEY, t);
    } catch {
      // ignore
    }
    applyTheme(t);
  }, []);

  const toggle = useCallback(() => {
    setThemeState((prev) => {
      const next: ThemeOption = prev === "light" ? "dark" : "light";
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch {
        // ignore
      }
      applyTheme(next);
      return next;
    });
  }, []);

  const resolved = theme === "auto" ? resolveSystemTheme() : theme;

  return { theme, resolved, setTheme, toggle };
}
