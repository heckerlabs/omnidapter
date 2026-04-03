import React from "react";
import { LogEntry } from "../../types";

interface EventLogProps {
  log: LogEntry[];
  onClear: () => void;
  logEndRef: React.RefObject<HTMLDivElement>;
  styles: Record<string, React.CSSProperties>;
}

export function EventLog({ log, onClear, logEndRef, styles }: EventLogProps) {
  return (
    <div style={styles.right} className="demo-log">
      <div style={styles.logHeader}>
        <h2 style={{ ...styles.sectionTitle, marginBottom: 0 }}>Event Log</h2>
        <button style={styles.clearBtn} onClick={onClear}>
          Clear
        </button>
      </div>
      <div style={styles.logPanel} className="demo-log-panel">
        {log.length === 0 && (
          <p style={styles.logEmpty}>Events will appear here once you connect.</p>
        )}
        {log.map((entry) => (
          <div
            key={entry.id}
            style={{
              ...styles.logEntry,
              borderLeftColor:
                entry.level === "success"
                  ? "#16a34a"
                  : entry.level === "error"
                  ? "#dc2626"
                  : "#9ca3af",
            }}
          >
            <span style={styles.logTime}>{entry.time}</span>
            <div style={styles.logContent}>
              <span
                style={{
                  color:
                    entry.level === "success"
                      ? "#15803d"
                      : entry.level === "error"
                      ? "#dc2626"
                      : "#374151",
                  fontWeight: entry.level !== "info" ? 500 : 400,
                }}
              >
                {entry.message}
              </span>
              {entry.detail && (
                <span style={styles.logDetail}>{entry.detail}</span>
              )}
            </div>
          </div>
        ))}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}
