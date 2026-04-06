/**
 * Connect UI API client.
 *
 * The bootstrap lt_ token is exchanged for a short-lived cs_ session token via
 * createSession() on mount.  All subsequent requests use the session token as
 * Bearer — it is held in memory only and never put back into any URL.
 */

import type { Provider } from "./types";

const BASE = "";

async function request<T>(method: string, path: string, token: string, body?: unknown): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        method,
        headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    const data = await res.json();

    if (!res.ok) {
        const err = data?.error ?? data?.detail ?? {};
        throw {
            status: res.status,
            code: err.code ?? "api_error",
            message: err.message ?? "Unknown error",
        };
    }

    return data as T;
}

/**
 * Exchange a one-time bootstrap lt_ token for a cs_ session token.
 *
 * The bootstrap token is passed in the request body — not as a Bearer header —
 * so it is never recorded in server access logs.  The session token is returned
 * and should be held in memory (and sessionStorage for OAuth round-trip survival).
 *
 * Throws on invalid/consumed/expired tokens with a typed error object.
 */
export interface SessionResult {
    sessionToken: string;
    redirectUri: string | null;
}

export async function createSession(bootstrapToken: string): Promise<SessionResult> {
    const res = await fetch("/connect/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: bootstrapToken }),
    });
    const data = await res.json();
    if (!res.ok) {
        // FastAPI error format uses `detail`; fall back to `error` for compatibility
        const detail = data as {
            detail?: { code?: string; message?: string };
            error?: { code?: string; message?: string };
        };
        const err = detail?.detail ?? detail?.error ?? {};
        throw {
            status: res.status,
            code: err.code ?? "api_error",
            message: err.message ?? "Unknown error",
        };
    }
    const d = (data as { data: { session_token: string; redirect_uri: string | null } }).data;
    return { sessionToken: d.session_token, redirectUri: d.redirect_uri ?? null };
}

export async function listProviders(token: string): Promise<Provider[]> {
    const data = await request<{ providers: Provider[] }>("GET", "/connect/providers", token);
    return data.providers;
}

export interface CreateConnectionResult {
    connection_id: string;
    status: string;
    authorization_url: string | null;
}

export async function createConnection(
    token: string,
    payload: {
        provider_key: string;
        redirect_uri?: string;
        credentials?: Record<string, string>;
    }
): Promise<CreateConnectionResult> {
    const data = await request<{ data: CreateConnectionResult }>(
        "POST",
        "/connect/connections",
        token,
        payload
    );
    return data.data;
}
