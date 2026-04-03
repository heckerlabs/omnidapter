import React, { useEffect, useState } from "react";
import type { PostMessageError } from "../types";

interface Props {
    code: string;
    message: string;
    isPopup: boolean;
    openerOrigin: string | null;
    redirectUri: string | null;
    onRetry?: () => void;
}

const RETRY_CODES = new Set(["user_denied", "invalid_credentials", "server_unreachable"]);
const REDIRECT_DELAY_S = 5;

export function ErrorView({ code, message, isPopup, openerOrigin, redirectUri, onRetry }: Props) {
    const canRetry = RETRY_CODES.has(code) && onRetry != null;
    const [countdown, setCountdown] = useState(REDIRECT_DELAY_S);

    useEffect(() => {
        if (canRetry) return;
        const canClose = (isPopup && window.opener && openerOrigin) || redirectUri;
        if (!canClose) return;

        const interval = setInterval(() => {
            setCountdown((n) => {
                if (n <= 1) {
                    clearInterval(interval);
                    if (isPopup && window.opener && openerOrigin) {
                        const msg: PostMessageError = { type: "omnidapter:error", code, message };
                        window.opener.postMessage(msg, openerOrigin);
                        window.close();
                    } else if (redirectUri) {
                        const url = new URL(redirectUri);
                        url.searchParams.set("error", code);
                        url.searchParams.set("error_description", message);
                        window.location.href = url.toString();
                    }
                    return 0;
                }
                return n - 1;
            });
        }, 1000);

        return () => clearInterval(interval);
    }, [canRetry, isPopup, openerOrigin, redirectUri, code, message]);

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
            {!canRetry && <p style={{ ...sub, marginTop: 16 }}>Sending you back in {countdown}…</p>}
        </div>
    );
}

const card: React.CSSProperties = {
    background: "var(--bg-card)",
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
    background: "var(--error)",
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
    color: "var(--text-main)",
};

const sub: React.CSSProperties = {
    color: "var(--text-sub)",
    fontSize: 14,
};

const retryBtn: React.CSSProperties = {
    marginTop: 20,
    padding: "8px 20px",
    background: "var(--primary)",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 500,
};
