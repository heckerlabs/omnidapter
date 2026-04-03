export function extractBootstrapToken(): string | null {
    const params = new URLSearchParams(window.location.search);
    return params.get("token");
}

export function extractOpenerOrigin(): string | null {
    const params = new URLSearchParams(window.location.search);
    const raw = params.get("opener_origin");
    if (!raw) return null;
    try {
        const url = new URL(raw);
        return url.origin;
    } catch {
        return null;
    }
}

export function extractOAuthReturn(): {
    connectionId: string | null;
    errorCode: string | null;
    errorMessage: string | null;
} {
    const params = new URLSearchParams(window.location.search);
    return {
        connectionId: params.get("connection_id"),
        errorCode: params.get("error"),
        errorMessage: params.get("error_description"),
    };
}

export function isPopup(): boolean {
    try {
        return window.opener !== null && window.opener !== window;
    } catch {
        return false;
    }
}

export function isInIframe(): boolean {
    try {
        return window !== window.top;
    } catch {
        return true;
    }
}

export function getCleanUrl(): string {
    const url = new URL(window.location.href);
    url.searchParams.delete("token");
    return url.toString();
}

export function getOAuthRedirectUri(): string {
    const redirectUri = new URL(window.location.href);
    redirectUri.search = "";
    redirectUri.hash = "";
    return redirectUri.toString();
}
