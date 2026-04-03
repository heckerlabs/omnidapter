import { useState, useEffect } from "react";
import { Theme } from "../types";
import { STORAGE_KEY } from "../constants";

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      const parsed = saved ? JSON.parse(saved) : null;
      return (["system", "light", "dark"] as Theme[]).includes(parsed?.theme)
        ? parsed.theme
        : "system";
    } catch {
      return "system";
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
  }, [theme]);

  const toggleTheme = () => {
    setTheme((t) => (t === "light" ? "dark" : t === "dark" ? "system" : "light"));
  };

  return { theme, toggleTheme };
}
