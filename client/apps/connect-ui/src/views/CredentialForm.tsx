import React, { useState } from "react";
import type { CredentialField, Provider } from "../types";

interface Props {
  provider: Provider;
  fieldErrors: Record<string, string>;
  formError: string | null;
  submitting: boolean;
  onSubmit: (values: Record<string, string>) => void;
  onBack: () => void;
}

export function CredentialFormView({
  provider,
  fieldErrors,
  formError,
  submitting,
  onSubmit,
  onBack,
}: Props) {
  const fields: CredentialField[] = provider.credential_schema?.fields ?? [];
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.key, ""]))
  );
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  // Merge local validation errors with server-side field errors (server takes priority)
  const mergedErrors = { ...localErrors, ...fieldErrors };

  const handleChange = (key: string, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    // Clear local error for this field once user starts typing
    if (localErrors[key]) {
      setLocalErrors((e) => {
        const r = { ...e };
        delete r[key];
        return r;
      });
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Client-side required validation
    const missing = fields.filter((f) => f.required && !values[f.key]?.trim());
    if (missing.length > 0) {
      const errors: Record<string, string> = {};
      missing.forEach((f) => {
        errors[f.key] = "Required";
      });
      setLocalErrors(errors);
      return;
    }
    setLocalErrors({});
    onSubmit(values);
  };

  return (
    <div style={card}>
      <button style={backBtn} onClick={onBack} type="button">
        ← Back
      </button>
      <h2 style={heading}>Connect {provider.name}</h2>
      {formError && <p style={formErrorBanner}>{formError}</p>}
      <form onSubmit={handleSubmit} noValidate>
        {fields.map((field) => (
          <div key={field.key} style={fieldWrapper}>
            <label style={labelStyle} htmlFor={field.key}>
              {field.label}
              {field.required && <span style={{ color: "var(--error)" }}> *</span>}
            </label>
            {field.type === "select" ? (
              <select
                id={field.key}
                value={values[field.key]}
                onChange={(e) => handleChange(field.key, e.target.value)}
                required={field.required}
                style={{
                  ...inputStyle,
                  borderColor: mergedErrors[field.key] ? "#ef4444" : "#d1d5db",
                }}
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
                  borderColor: mergedErrors[field.key] ? "#ef4444" : "#d1d5db",
                }}
              />
            )}
            {mergedErrors[field.key] && (
              <p style={errorText}>{mergedErrors[field.key]}</p>
            )}
            {field.help_text && !mergedErrors[field.key] && (
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
  background: "var(--bg-card)",
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
  color: "var(--text-sub)",
  cursor: "pointer",
  fontSize: 14,
  padding: 0,
  marginBottom: 16,
};

const heading: React.CSSProperties = {
  fontSize: 20,
  fontWeight: 600,
  marginBottom: 20,
  color: "var(--text-main)",
};

const fieldWrapper: React.CSSProperties = {
  marginBottom: 16,
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 14,
  fontWeight: 500,
  marginBottom: 4,
  color: "var(--text-main)",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  border: "1px solid var(--border)",
  borderRadius: 6,
  fontSize: 14,
  outline: "none",
  background: "var(--input-bg)",
  color: "var(--text-main)",
};

const helpText: React.CSSProperties = {
  fontSize: 12,
  color: "var(--text-sub)",
  marginTop: 4,
};

const errorText: React.CSSProperties = {
  fontSize: 12,
  color: "var(--error)",
  marginTop: 4,
};

const submitBtn: React.CSSProperties = {
  width: "100%",
  padding: "10px",
  background: "var(--primary)",
  color: "#fff",
  border: "none",
  borderRadius: 8,
  fontSize: 15,
  fontWeight: 600,
  cursor: "pointer",
  marginTop: 8,
};

const formErrorBanner: React.CSSProperties = {
  padding: "12px",
  background: "var(--error-bg)",
  border: "1px solid var(--error-border)",
  borderRadius: 6,
  color: "var(--error-text)",
  fontSize: 14,
  marginBottom: 16,
};
