import React, { useState } from "react";

interface FieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  warning?: string;
  styles: Record<string, React.CSSProperties>;
}

export function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  warning,
  styles,
}: FieldProps) {
  const [tipVisible, setTipVisible] = useState(false);
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={styles.fieldLabel}>{label}</label>
      <div style={{ position: "relative" }}>
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          style={{ ...styles.input, ...(warning ? { paddingRight: 28 } : {}) }}
          spellCheck={false}
          autoComplete="off"
        />
        {warning && (
          <span
            style={styles.warnIcon}
            onMouseEnter={() => setTipVisible(true)}
            onMouseLeave={() => setTipVisible(false)}
          >
            ⚠
            {tipVisible && <span style={styles.warnTooltip}>{warning}</span>}
          </span>
        )}
      </div>
    </div>
  );
}
