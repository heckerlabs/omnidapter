import React from "react";
import { Theme } from "../../types";

interface HeaderProps {
  theme: Theme;
  onToggleTheme: () => void;
  styles: Record<string, React.CSSProperties>;
}

export function Header({ theme, onToggleTheme, styles }: HeaderProps) {
  return (
    <header style={styles.header}>
      <div>
        <h1 style={styles.title} className="demo-title">
          Omnidapter Connect Demo
        </h1>
        <p style={styles.subtitle}>Test all Connect UI integration modes</p>
      </div>
      <button
        style={styles.themeBtn}
        onClick={onToggleTheme}
        title={theme === "light" ? "Light" : theme === "dark" ? "Dark" : "System"}
      >
        {theme === "light" ? "☀" : theme === "dark" ? "☾" : "◑"}
      </button>
    </header>
  );
}
