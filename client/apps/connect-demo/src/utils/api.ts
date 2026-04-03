import { Config } from "../types";

export async function fetchLinkToken(
    config: Config,
    redirectUri: string | undefined
): Promise<string> {
    const body: Record<string, unknown> = {
        end_user_id: config.endUserId || "demo_user",
    };
    if (config.allowedProviders.trim()) {
        body.allowed_providers = config.allowedProviders
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);
    }
    if (redirectUri) {
        body.redirect_uri = redirectUri;
    }

    const res = await fetch(`${config.apiUrl}/v1/link-tokens`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${config.apiKey}`,
        },
        body: JSON.stringify(body),
    });

    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const msg =
            (data as { detail?: { message?: string }; error?: { message?: string } })?.detail
                ?.message ??
            (data as { error?: { message?: string } })?.error?.message ??
            `HTTP ${res.status}`;
        throw new Error(msg);
    }

    const data = (await res.json()) as { data: { token: string } };
    return data.data.token;
}
