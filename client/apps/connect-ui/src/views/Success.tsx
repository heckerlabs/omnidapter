import React, { useEffect } from "react";
import type { PostMessageSuccess } from "../types";

interface Props {
  connectionId: string;
  provider: string;
  redirectUri: string | null;
  isPopup: boolean;
  openerOrigin: string | null;
}

export function SuccessView({ connectionId, provider, redirectUri, isPopup, openerOrigin }: Props) {
  useEffect(() => {
    if (isPopup && window.opener && openerOrigin) {
      const msg: PostMessageSuccess = {
        type: "omnidapter:success",
        connectionId,
        provider,
      };
      window.opener.postMessage(msg, openerOrigin);
      setTimeout(() => window.close(), 300);
    } else if (redirectUri) {
      const url = new URL(redirectUri);
      url.searchParams.set("connection_id", connectionId);
      url.searchParams.set("status", "active");
      setTimeout(() => {
        window.location.href = url.toString();
      }, 1500);
    }
  }, [connectionId, isPopup, provider, redirectUri]);

  return (
    <div style={card}>
      <div style={check}>✓</div>
      <h2 style={heading}>Connected!</h2>
      <p style={sub}>Your calendar has been connected successfully.</p>
      {!isPopup && redirectUri && (
        <p style={{ ...sub, marginTop: 8 }}>Redirecting you back…</p>
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
};

const check: React.CSSProperties = {
  width: 48,
  height: 48,
  background: "#10b981",
  color: "#fff",
  borderRadius: "50%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: 24,
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
