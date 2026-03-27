import React, { useState } from "react";
import type { CredentialField, Provider } from "../types";

interface Props {
  provider: Provider;
  fieldErrors: Record<string, string>;
  submitting: boolean;
  onSubmit: (values: Record<string, string>) => void;
  onBack: () => void;
}

export function CredentialFormView({
  provider,
  fieldErrors,
  submitting,
  onSubmit,
  onBack,
}: Props) {
  const fields: CredentialField[] = provider.credential_schema?.fields ?? [];
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.key, ""]))
  );

  const handleChange = (key: string, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Client-side required validation
    const missing = fields.filter((f) => f.required && !values[f.key]?.trim());
    if (missing.length > 0) return; // HTML5 required handles this
    onSubmit(values);
  };

  return (
    <div style={card}>
      <button style={backBtn} onClick={onBack} type="button">
        ← Back
      </button>
      <h2 style={heading}>Connect {provider.name}</h2>
      <form onSubmit={handleSubmit} noValidate>
        {fields.map((field) => (
          <div key={field.key} style={fieldWrapper}>
            <label style={labelStyle} htmlFor={field.key}>
              {field.label}
              {field.required && <span style={{ color: "#ef4444" }}> *</span>}
            </label>
            {field.type === "select" ? (
              <select
                id={field.key}
                value={values[field.key]}
                onChange={(e) => handleChange(field.key, e.target.value)}
                required={field.required}
                style={inputStyle}
              >
                <option value="">Select…</option>
                {(field.options ?? []).map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={field.key}
                type={field.type}
                value={values[field.key]}
                onChange={(e) => handleChange(field.key, e.target.value)}
                placeholder={field.placeholder}
                required={field.required}
                style={{
                  ...inputStyle,
                  borderColor: fieldErrors[field.key] ? "#ef4444" : "#d1d5db",
                }}
              />
            )}
            {fieldErrors[field.key] && (
              <p style={errorText}>{fieldErrors[field.key]}</p>
            )}
            {field.help_text && !fieldErrors[field.key] && (
              <p style={helpText}>{field.help_text}</p>
            )}
          </div>
        ))}
        <button type="submit" style={submitBtn} disabled={submitting}>
          {submitting ? "Connecting…" : "Connect"}
        </button>
      </form>
    </div>
  );
}

const card: React.CSSProperties = {
  background: "#fff",
  borderRadius: 12,
  padding: "32px 40px",
  boxShadow: "0 1px 3px rgba(0,0,0,.1)",
  minWidth: 340,
  maxWidth: 440,
  width: "100%",
};

const backBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#6b7280",
  cursor: "pointer",
  fontSize: 14,
  padding: 0,
  marginBottom: 16,
};

const heading: React.CSSProperties = {
  fontSize: 20,
  fontWeight: 600,
  marginBottom: 20,
};

const fieldWrapper: React.CSSProperties = {
  marginBottom: 16,
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 14,
  fontWeight: 500,
  marginBottom: 4,
  color: "#374151",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  fontSize: 14,
  outline: "none",
};

const helpText: React.CSSProperties = {
  fontSize: 12,
  color: "#6b7280",
  marginTop: 4,
};

const errorText: React.CSSProperties = {
  fontSize: 12,
  color: "#ef4444",
  marginTop: 4,
};

const submitBtn: React.CSSProperties = {
  width: "100%",
  padding: "10px",
  background: "#6366f1",
  color: "#fff",
  border: "none",
  borderRadius: 8,
  fontSize: 15,
  fontWeight: 600,
  cursor: "pointer",
  marginTop: 8,
};
