import React from "react";
import type { Provider } from "../types";

interface Props {
    providers: Provider[];
    onSelect: (provider: Provider) => void;
    onCancel: () => void;
}

export function ProviderSelectionView({ providers, onSelect, onCancel }: Props) {
    if (providers.length === 0) {
        return (
            <div style={card}>
                <h2 style={heading}>No providers available</h2>
                <p style={sub}>
                    No calendar providers are currently available. Please contact support.
                </p>
            </div>
        );
    }

    return (
        <div style={card}>
            <h2 style={heading}>Connect a Calendar</h2>
            <p style={sub}>Choose a calendar provider to connect.</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 24 }}>
                {providers.map((p) => (
                    <button key={p.key} style={providerBtn} onClick={() => onSelect(p)}>
                        <span style={providerIcon}>{p.name[0]}</span>
                        <span style={{ fontWeight: 500 }}>{p.name}</span>
                    </button>
                ))}
            </div>
            <button style={cancelBtn} onClick={onCancel}>
                Cancel
            </button>
        </div>
    );
}

const card: React.CSSProperties = {
    background: "var(--bg-card)",
    borderRadius: 12,
    padding: "40px",
    boxShadow: "0 1px 3px rgba(0,0,0,.1)",
    minWidth: 340,
    maxWidth: 420,
    width: "100%",
};

const heading: React.CSSProperties = {
    fontSize: 20,
    fontWeight: 600,
    marginBottom: 6,
    color: "var(--text-main)",
};

const sub: React.CSSProperties = {
    color: "var(--text-sub)",
    fontSize: 14,
};

const providerBtn: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 16px",
    border: "1px solid var(--border)",
    borderRadius: 8,
    background: "var(--bg-card)",
    color: "var(--text-main)",
    cursor: "pointer",
    fontSize: 15,
    textAlign: "left",
    transition: "border-color 0.15s, background-color 0.15s",
};

const cancelBtn: React.CSSProperties = {
    marginTop: 20,
    width: "100%",
    padding: "8px 0",
    background: "transparent",
    color: "var(--text-sub)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 14,
};

const providerIcon: React.CSSProperties = {
    width: 32,
    height: 32,
    borderRadius: "50%",
    background: "var(--primary)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 700,
    fontSize: 14,
    flexShrink: 0,
};
