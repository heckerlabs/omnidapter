import { useReducer } from "react";
import type { AppState, Provider } from "../types";
import { extractOpenerOrigin } from "../utils/window";

export type Action =
    | { type: "SESSION_READY"; token: string; redirectUri: string | null }
    | { type: "PROVIDERS_LOADED"; providers: Provider[] }
    | { type: "PROVIDERS_EMPTY" }
    | { type: "LOAD_ERROR"; code: string; message: string }
    | { type: "SELECT_PROVIDER"; provider: Provider }
    | { type: "OAUTH_REDIRECT_STARTED" }
    | {
          type: "OAUTH_RETURN_SUCCESS";
          connectionId: string;
          provider: string;
          services: string[];
          redirectUri: string | null;
          openerOrigin: string | null;
      }
    | { type: "OAUTH_RETURN_ERROR"; code: string; message: string }
    | { type: "CREDENTIAL_SUBMIT_START" }
    | { type: "CREDENTIAL_SUBMIT_SUCCESS"; connectionId: string }
    | { type: "CREDENTIAL_SUBMIT_ERROR"; fieldErrors: Record<string, string>; message: string }
    | { type: "RETRY" };

const initialState: AppState = {
    view: "loading",
    token: null,
    openerOrigin: extractOpenerOrigin(),
    redirectUri: null,
    providers: [],
    selectedProvider: null,
    oauthProvider: null,
    oauthProviderServices: [],
    connectionId: null,
    errorCode: null,
    errorMessage: null,
    fieldErrors: {},
    formError: null,
    submitting: false,
};

function reducer(state: AppState, action: Action): AppState {
    switch (action.type) {
        case "SESSION_READY":
            return { ...state, token: action.token, redirectUri: action.redirectUri };

        case "PROVIDERS_LOADED":
            if (action.providers.length === 1) {
                const p = action.providers[0];
                return {
                    ...state,
                    providers: action.providers,
                    selectedProvider: p,
                    view: p.credential_schema ? "credential_form" : "oauth_init",
                };
            }
            return { ...state, providers: action.providers, view: "provider_selection" };

        case "PROVIDERS_EMPTY":
            return {
                ...state,
                view: "error",
                errorCode: "no_providers",
                errorMessage: "No providers are available for this session.",
            };

        case "LOAD_ERROR":
            return {
                ...state,
                view: "error",
                errorCode: action.code,
                errorMessage: action.message,
            };

        case "SELECT_PROVIDER":
            return {
                ...state,
                selectedProvider: action.provider,
                view: action.provider.credential_schema ? "credential_form" : "oauth_init",
                fieldErrors: {},
            };

        case "OAUTH_REDIRECT_STARTED":
            return { ...state, view: "oauth_init" };

        case "OAUTH_RETURN_SUCCESS":
            return {
                ...state,
                view: "success",
                connectionId: action.connectionId,
                oauthProvider: action.provider,
                oauthProviderServices: action.services,
                redirectUri: action.redirectUri ?? state.redirectUri,
                openerOrigin: action.openerOrigin ?? state.openerOrigin,
            };

        case "OAUTH_RETURN_ERROR":
            return {
                ...state,
                view: "error",
                errorCode: action.code,
                errorMessage: action.message,
            };

        case "CREDENTIAL_SUBMIT_START":
            return { ...state, fieldErrors: {}, formError: null, submitting: true };

        case "CREDENTIAL_SUBMIT_SUCCESS":
            return {
                ...state,
                view: "success",
                connectionId: action.connectionId,
                submitting: false,
            };

        case "CREDENTIAL_SUBMIT_ERROR":
            return {
                ...state,
                fieldErrors: action.fieldErrors,
                formError: action.message,
                submitting: false,
            };

        case "RETRY": {
            if (state.providers.length > 1) {
                return {
                    ...state,
                    view: "provider_selection",
                    errorCode: null,
                    errorMessage: null,
                    fieldErrors: {},
                };
            }
            const provider = state.selectedProvider ?? state.providers[0] ?? null;
            return {
                ...state,
                view: provider?.credential_schema ? "credential_form" : "oauth_init",
                errorCode: null,
                errorMessage: null,
                fieldErrors: {},
            };
        }

        default:
            return state;
    }
}

export function useAppReducer() {
    return useReducer(reducer, initialState);
}
