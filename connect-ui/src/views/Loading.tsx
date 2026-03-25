import React from "react";

export function LoadingView() {
  return (
    <div style={card}>
      <div style={spinner} />
      <p style={{ color: "#6b7280", marginTop: 16 }}>Loading…</p>
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

const spinner: React.CSSProperties = {
  width: 36,
  height: 36,
  border: "3px solid #e5e7eb",
  borderTopColor: "#6366f1",
  borderRadius: "50%",
  animation: "spin 0.8s linear infinite",
  margin: "0 auto",
};
