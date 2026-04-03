import React from "react";
import { Mode } from "../../types";

interface ModeTabsProps {
  mode: Mode;
  setMode: (mode: Mode) => void;
  styles: Record<string, React.CSSProperties>;
}

export function ModeTabs({ mode, setMode, styles }: ModeTabsProps) {
  const modeDesc: Record<Mode, string> = {
    popup: "Opens Connect UI in a centered popup window. Communicates result via postMessage.",
    redirect: "Navigates the full page to Connect UI, then redirects back with connection_id.",
    embed: "Renders Connect UI inside an iframe modal. Result returned via postMessage.",
  };

  return (
    <section style={styles.section}>
      <h2 style={styles.sectionTitle}>Mode</h2>
      <div style={styles.tabs}>
        {(["popup", "redirect", "embed"] as Mode[]).map((m) => (
          <button
            key={m}
            style={{ ...styles.tab, ...(mode === m ? styles.tabActive : {}) }}
            onClick={() => setMode(m)}
          >
            {m === "popup" ? "🪟 Popup" : m === "redirect" ? "↗ Redirect" : "🖼 Embed"}
          </button>
        ))}
      </div>
      <p style={styles.modeDesc}>{modeDesc[mode]}</p>
    </section>
  );
}
