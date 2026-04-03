import React, { useEffect, useState } from "react";
import type { PostMessageSuccess } from "../types";

interface Props {
    connectionId: string;
    provider: string;
    redirectUri: string | null;
    isPopup: boolean;
    openerOrigin: string | null;
}

const REDIRECT_DELAY_S = 5;

export function SuccessView({ connectionId, provider, redirectUri, isPopup, openerOrigin }: Props) {
    const [countdown, setCountdown] = useState(REDIRECT_DELAY_S);

    useEffect(() => {
        const msg: PostMessageSuccess = { type: "omnidapter:success", connectionId, provider };

        // Redirect / embed: navigate immediately, no countdown.
        if (!isPopup && redirectUri) {
            const url = new URL(redirectUri);
            url.searchParams.set("connection_id", connectionId);
            url.searchParams.set("status", "active");
            window.location.href = url.toString();
            return;
        }

        // Popup: postMessage immediately, then close after countdown.
        if (isPopup && window.opener && openerOrigin) {
            window.opener.postMessage(msg, openerOrigin);

            const interval = setInterval(() => {
                setCountdown((n) => {
                    if (n <= 1) {
                        clearInterval(interval);
                        window.close();
                        return 0;
                    }
                    return n - 1;
                });
            }, 1000);

            return () => clearInterval(interval);
        }
    }, [connectionId, isPopup, provider, redirectUri, openerOrigin]);

    return (
        <div style={card}>
            <div style={check}>✓</div>
            <h2 style={heading}>Connected!</h2>
            <p style={sub}>Your calendar has been connected successfully.</p>
            {isPopup && <p style={{ ...sub, marginTop: 8 }}>Sending you back in {countdown}…</p>}
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
};

const check: React.CSSProperties = {
    width: 48,
    height: 48,
    background: "var(--success)",
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
    color: "var(--text-main)",
};

const sub: React.CSSProperties = {
    color: "var(--text-sub)",
    fontSize: 14,
};
