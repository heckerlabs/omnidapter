import React from "react";
import type { Provider } from "../types";

interface Props {
  provider: Provider;
}

export function OAuthInitView({ provider }: Props) {
  return (
    <div style={card}>
      <div style={spinner} />
      <h2 style={heading}>Redirecting to {provider.name}…</h2>
      <p style={sub}>
        You're being redirected to {provider.name} to authorize access.
      </p>
    </div>
  );
}

const card: React.CSSProperties = {
  background: "#fff",
  borderRadius: 12,
  padding: "48px 40px",
  boxShadow: "0 1px 3px rgba(0,0,0,.1)",
  textAlign: "center",
  minWidth: 340,
};

const heading: React.CSSProperties = {
  fontSize: 18,
  fontWeight: 600,
  margin: "16px 0 8px",
};

const sub: React.CSSProperties = {
  color: "#6b7280",
  fontSize: 14,
};

const spinner: React.CSSProperties = {
  width: 36,
  height: 36,
  border: "3px solid #e5e7eb",
  borderTopColor: "#6366f1",
  borderRadius: "50%",
  animation: "spin 0.8s linear infinite",
  margin: "0 auto",
};
