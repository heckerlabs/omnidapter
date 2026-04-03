/**
 * Tests for api.ts — especially createSession() error parsing.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { createSession, listProviders, createConnection } from "../api";

afterEach(() => {
    vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// createSession
// ---------------------------------------------------------------------------

describe("createSession", () => {
    it("returns the session token on success", async () => {
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(
                JSON.stringify({ data: { session_token: "cs_abc123", expires_in: 900 } }),
                {
                    status: 200,
                    headers: { "Content-Type": "application/json" },
                }
            )
        );

        const token = await createSession("lt_bootstrap");
        expect(token.sessionToken).toBe("cs_abc123");
        expect(token.redirectUri).toBe(null);
    });

    it("throws with code and message from FastAPI detail on failure", async () => {
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(
                JSON.stringify({
                    detail: { code: "token_already_used", message: "Link already opened." },
                }),
                { status: 401, headers: { "Content-Type": "application/json" } }
            )
        );

        await expect(createSession("lt_used")).rejects.toMatchObject({
            status: 401,
            code: "token_already_used",
            message: "Link already opened.",
        });
    });

    it("throws with code from detail.code for session_expired", async () => {
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(
                JSON.stringify({
                    detail: { code: "session_expired", message: "Invalid or expired link token" },
                }),
                { status: 401, headers: { "Content-Type": "application/json" } }
            )
        );

        await expect(createSession("lt_expired")).rejects.toMatchObject({
            status: 401,
            code: "session_expired",
        });
    });

    it("falls back to generic api_error when detail is absent", async () => {
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(JSON.stringify({ message: "Internal Server Error" }), {
                status: 500,
                headers: { "Content-Type": "application/json" },
            })
        );

        await expect(createSession("lt_x")).rejects.toMatchObject({
            status: 500,
            code: "api_error",
        });
    });
});

// ---------------------------------------------------------------------------
// listProviders — basic error handling
// ---------------------------------------------------------------------------

describe("listProviders", () => {
    it("returns providers array on success", async () => {
        const providers = [
            { key: "google", name: "Google", auth_kind: "oauth2", credential_schema: null },
        ];
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(JSON.stringify({ providers }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            })
        );

        const result = await listProviders("cs_session");
        expect(result).toEqual(providers);
    });

    it("throws with session_expired code when 401 with that code", async () => {
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(
                JSON.stringify({ detail: { code: "session_expired", message: "Session expired" } }),
                { status: 401, headers: { "Content-Type": "application/json" } }
            )
        );

        await expect(listProviders("cs_stale")).rejects.toMatchObject({
            code: "session_expired",
        });
    });
});

// ---------------------------------------------------------------------------
// createConnection — basic success
// ---------------------------------------------------------------------------

describe("createConnection", () => {
    it("returns connection data on OAuth init success", async () => {
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(
                JSON.stringify({
                    data: {
                        connection_id: "conn_abc",
                        status: "pending",
                        authorization_url: "https://accounts.google.com/o/oauth2/auth?state=xyz",
                    },
                }),
                { status: 201, headers: { "Content-Type": "application/json" } }
            )
        );

        const result = await createConnection("cs_session", { provider_key: "google" });
        expect(result.connection_id).toBe("conn_abc");
        expect(result.authorization_url).toContain("accounts.google.com");
    });
});
