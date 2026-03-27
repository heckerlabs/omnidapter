import React from "react";
import type { PostMessageError } from "../types";

interface Props {
  code: string;
  message: string;
  isPopup: boolean;
  openerOrigin: string | null;
  onRetry?: () => void;
}

const RETRY_CODES = new Set(["user_denied", "invalid_credentials", "server_unreachable"]);

export function ErrorView({ code, message, isPopup, openerOrigin, onRetry }: Props) {
  const canRetry = RETRY_CODES.has(code) && onRetry != null;

  const handleClose = () => {
    if (isPopup && window.opener && openerOrigin) {
      const msg: PostMessageError = { type: "omnidapter:error", code, message };
      window.opener.postMessage(msg, openerOrigin);
      window.close();
    }
  };

  return (
    <div style={card}>
      <div style={icon}>✕</div>
      <h2 style={heading}>Something went wrong</h2>
      <p style={sub}>{message}</p>
      {canRetry && (
        <button style={retryBtn} onClick={onRetry}>
          Try again
        </button>
      )}
      {isPopup && (
        <button style={closeBtn} onClick={handleClose}>
          Close
        </button>
      )}
      {!isPopup && !canRetry && (
        <p style={{ ...sub, marginTop: 16 }}>
          Please return to the application and try again.
        </p>
      )}
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
  maxWidth: 420,
};

const icon: React.CSSProperties = {
  width: 48,
  height: 48,
  background: "#ef4444",
  color: "#fff",
  borderRadius: "50%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: 20,
  margin: "0 auto 16px",
  fontWeight: 700,
};

const heading: React.CSSProperties = {
  fontSize: 20,
  fontWeight: 600,
  marginBottom: 8,
};

const sub: React.CSSProperties = {
  color: "#6b7280",
  fontSize: 14,
};

const retryBtn: React.CSSProperties = {
  marginTop: 20,
  padding: "8px 20px",
  background: "#6366f1",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 14,
  fontWeight: 500,
};

const closeBtn: React.CSSProperties = {
  marginTop: 12,
  padding: "8px 20px",
  background: "transparent",
  color: "#6b7280",
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 14,
};
