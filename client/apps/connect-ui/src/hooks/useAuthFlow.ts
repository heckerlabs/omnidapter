import { useEffect, useRef, Dispatch } from "react";
import { createSession, listProviders, createConnection } from "../api";
import type { AppState } from "../types";
import type { Action } from "./useAppReducer";
import {
    extractOAuthReturn,
    extractBootstrapToken,
    getCleanUrl,
    getOAuthRedirectUri,
    isInIframe,
} from "../utils/window";
import {
    SESSION_STORAGE_KEY,
    PROVIDER_KEY_STORAGE,
    PROVIDER_SERVICES_STORAGE,
    REDIRECT_URI_STORAGE,
    OPENER_ORIGIN_STORAGE,
    EMBED_OAUTH_STORAGE,
} from "../constants";

export function useAuthFlow(state: AppState, dispatch: Dispatch<Action>) {
    const bootstrapRan = useRef(false);

    useEffect(() => {
        if (bootstrapRan.current) return;
        bootstrapRan.current = true;
        const { connectionId, errorCode, errorMessage } = extractOAuthReturn();

        if (
            connectionId &&
            !errorCode &&
            window.opener &&
            localStorage.getItem(EMBED_OAUTH_STORAGE) === "true"
        ) {
            localStorage.removeItem(EMBED_OAUTH_STORAGE);
            const opener = window.opener as Window;
            const savedProviderKey = opener.sessionStorage.getItem(PROVIDER_KEY_STORAGE) ?? "";
            const savedRedirectUri = opener.sessionStorage.getItem(REDIRECT_URI_STORAGE);
            opener.postMessage(
                {
                    type: "omnidapter:oauth_complete",
                    connectionId,
                    provider: savedProviderKey,
                    redirectUri: savedRedirectUri,
                },
                window.location.origin
            );
            window.close();
            return;
        }

        if (connectionId && !errorCode) {
            const savedProviderKey = sessionStorage.getItem(PROVIDER_KEY_STORAGE) ?? "";
            const savedProviderServices: string[] = JSON.parse(
                sessionStorage.getItem(PROVIDER_SERVICES_STORAGE) ?? "[]"
            );
            const savedRedirectUri = sessionStorage.getItem(REDIRECT_URI_STORAGE);
            const savedOpenerOrigin = sessionStorage.getItem(OPENER_ORIGIN_STORAGE);
            sessionStorage.removeItem(PROVIDER_KEY_STORAGE);
            sessionStorage.removeItem(PROVIDER_SERVICES_STORAGE);
            sessionStorage.removeItem(REDIRECT_URI_STORAGE);
            sessionStorage.removeItem(OPENER_ORIGIN_STORAGE);
            const savedSession = sessionStorage.getItem(SESSION_STORAGE_KEY);
            if (savedSession) {
                dispatch({
                    type: "SESSION_READY",
                    token: savedSession,
                    redirectUri: savedRedirectUri,
                });
            }
            dispatch({
                type: "OAUTH_RETURN_SUCCESS",
                connectionId,
                provider: savedProviderKey,
                services: savedProviderServices,
                redirectUri: savedRedirectUri,
                openerOrigin: savedOpenerOrigin,
            });
            return;
        }

        if (errorCode) {
            dispatch({
                type: "OAUTH_RETURN_ERROR",
                code: errorCode,
                message: errorMessage ?? "Authorization was denied.",
            });
            return;
        }

        const bootstrapToken = extractBootstrapToken();
        if (!bootstrapToken) {
            dispatch({
                type: "LOAD_ERROR",
                code: "missing_token",
                message: "No link token provided. Please return to the application.",
            });
            return;
        }

        window.history.replaceState({}, "", getCleanUrl());

        createSession(bootstrapToken)
            .then(({ sessionToken, redirectUri }) => {
                sessionStorage.setItem(SESSION_STORAGE_KEY, sessionToken);
                if (redirectUri) {
                    sessionStorage.setItem(REDIRECT_URI_STORAGE, redirectUri);
                }
                dispatch({ type: "SESSION_READY", token: sessionToken, redirectUri });
            })
            .catch((err: { code?: string; message?: string }) => {
                dispatch({
                    type: "LOAD_ERROR",
                    code: err.code ?? "session_error",
                    message: err.message ?? "Failed to start session.",
                });
            });
    }, [dispatch]);

    useEffect(() => {
        if (state.view !== "loading" || !state.token) return;

        listProviders(state.token)
            .then((providers) => {
                if (providers.length === 0) {
                    dispatch({ type: "PROVIDERS_EMPTY" });
                } else {
                    dispatch({ type: "PROVIDERS_LOADED", providers });
                }
            })
            .catch((err: { code?: string; message?: string }) => {
                dispatch({
                    type: "LOAD_ERROR",
                    code: err.code ?? "load_error",
                    message: err.message ?? "Failed to load providers.",
                });
            });
    }, [state.token, state.view, dispatch]);

    useEffect(() => {
        if (state.view !== "oauth_init" || !state.selectedProvider || !state.token) return;

        sessionStorage.setItem(PROVIDER_KEY_STORAGE, state.selectedProvider.key);
        sessionStorage.setItem(
            PROVIDER_SERVICES_STORAGE,
            JSON.stringify(state.selectedProvider.services ?? [])
        );
        if (state.openerOrigin) {
            sessionStorage.setItem(OPENER_ORIGIN_STORAGE, state.openerOrigin);
        }

        createConnection(state.token, {
            provider_key: state.selectedProvider.key,
            redirect_uri: getOAuthRedirectUri(),
        })
            .then((result) => {
                if (result.authorization_url) {
                    if (isInIframe()) {
                        localStorage.setItem(EMBED_OAUTH_STORAGE, "true");
                        const w = 520,
                            h = 640;
                        const left = Math.round(
                            Math.max(0, (screen.width - w) / 2 + (window.screenX ?? 0))
                        );
                        const top = Math.round(
                            Math.max(0, (screen.height - h) / 2 + (window.screenY ?? 0))
                        );
                        window.open(
                            result.authorization_url,
                            "omnidapter_oauth",
                            `width=${w},height=${h},left=${left},top=${top},resizable=yes,scrollbars=yes`
                        );
                    } else {
                        window.location.href = result.authorization_url;
                    }
                }
            })
            .catch((err: { code?: string; message?: string }) => {
                dispatch({
                    type: "LOAD_ERROR",
                    code: err.code ?? "oauth_error",
                    message: err.message ?? "Failed to start OAuth flow.",
                });
            });
    }, [state.view, state.selectedProvider, state.token, state.openerOrigin, dispatch]);

    useEffect(() => {
        if (!isInIframe()) return;

        const handler = (event: MessageEvent) => {
            if (event.origin !== window.location.origin) return;
            const data = event.data as {
                type?: string;
                connectionId?: string;
                provider?: string;
                redirectUri?: string | null;
            };
            if (data?.type !== "omnidapter:oauth_complete") return;

            const savedSession = sessionStorage.getItem(SESSION_STORAGE_KEY);
            const savedRedirectUri = sessionStorage.getItem(REDIRECT_URI_STORAGE);
            const savedProviderServices: string[] = JSON.parse(
                sessionStorage.getItem(PROVIDER_SERVICES_STORAGE) ?? "[]"
            );
            sessionStorage.removeItem(PROVIDER_KEY_STORAGE);
            sessionStorage.removeItem(PROVIDER_SERVICES_STORAGE);
            sessionStorage.removeItem(REDIRECT_URI_STORAGE);
            sessionStorage.removeItem(OPENER_ORIGIN_STORAGE);

            if (savedSession) {
                dispatch({
                    type: "SESSION_READY",
                    token: savedSession,
                    redirectUri: data.redirectUri ?? savedRedirectUri,
                });
            }
            dispatch({
                type: "OAUTH_RETURN_SUCCESS",
                connectionId: data.connectionId ?? "",
                provider: data.provider ?? "",
                services: savedProviderServices,
                redirectUri: data.redirectUri ?? savedRedirectUri,
                openerOrigin: null,
            });
        };

        window.addEventListener("message", handler);
        return () => window.removeEventListener("message", handler);
    }, [dispatch]);
}
