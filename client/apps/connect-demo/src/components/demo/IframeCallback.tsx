import React from "react";

interface IframeCallbackProps {
  connectionId: string | null;
  styles: Record<string, React.CSSProperties>;
}

export function IframeCallback({ connectionId, styles }: IframeCallbackProps) {
  return (
    <div style={styles.iframeCallback}>
      <span style={{ color: connectionId ? "#16a34a" : "#dc2626", fontSize: 32 }}>
        {connectionId ? "✓" : "✕"}
      </span>
      <p style={{ marginTop: 8, color: "#555", fontSize: 14 }}>
        {connectionId ? "Connected! Returning…" : "Error. Returning…"}
      </p>
    </div>
  );
}
