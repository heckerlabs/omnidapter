import { useEffect, useReducer } from "react";
import { listProviders, createConnection } from "./api";
import { LoadingView } from "./views/Loading";
import { ProviderSelectionView } from "./views/ProviderSelection";
import { OAuthInitView } from "./views/OAuthInit";
import { CredentialFormView } from "./views/CredentialForm";
import { SuccessView } from "./views/Success";
import { ErrorView } from "./views/Error";
import type { AppState, Provider } from "./types";

// ---------------------------------------------------------------------------
// Token extraction — the SPA receives the link token via URL parameter on
// first load, then holds it in memory only.
// ---------------------------------------------------------------------------

function extractToken(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get("token");
}

function extractOpenerOrigin(): string | null {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get("opener_origin");
  if (!raw) return null;
  try {
    // Validate it's a real origin (scheme + host), not an arbitrary string
    const url = new URL(raw);
    return url.origin;
  } catch {
    return null;
  }
}

function extractOAuthReturn(): {
  connectionId: string | null;
  status: string | null;
  errorCode: string | null;
  errorMessage: string | null;
} {
  const params = new URLSearchParams(window.location.search);
  return {
    connectionId: params.get("connection_id"),
    status: params.get("status"),
    errorCode: params.get("error"),
    errorMessage: params.get("error_description"),
  };
}

function isPopup(): boolean {
  try {
    return window.opener !== null && window.opener !== window;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// State reducer
// ---------------------------------------------------------------------------

type Action =
  | { type: "PROVIDERS_LOADED"; providers: Provider[] }
  | { type: "PROVIDERS_EMPTY" }
  | { type: "LOAD_ERROR"; code: string; message: string }
  | { type: "SELECT_PROVIDER"; provider: Provider }
  | { type: "OAUTH_REDIRECT_STARTED" }
  | { type: "OAUTH_RETURN_SUCCESS"; connectionId: string; provider: string }
  | { type: "OAUTH_RETURN_ERROR"; code: string; message: string }
  | { type: "CREDENTIAL_SUBMIT_START" }
  | { type: "CREDENTIAL_SUBMIT_SUCCESS"; connectionId: string }
  | { type: "CREDENTIAL_SUBMIT_ERROR"; fieldErrors: Record<string, string>; message: string }
  | { type: "RETRY" };

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
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
      return { ...state, view: "error", errorCode: action.code, errorMessage: action.message };

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
      return { ...state, view: "success", connectionId: action.connectionId };

    case "OAUTH_RETURN_ERROR":
      return { ...state, view: "error", errorCode: action.code, errorMessage: action.message };

    case "CREDENTIAL_SUBMIT_START":
      return { ...state, fieldErrors: {}, submitting: true };

    case "CREDENTIAL_SUBMIT_SUCCESS":
      return { ...state, view: "success", connectionId: action.connectionId, submitting: false };

    case "CREDENTIAL_SUBMIT_ERROR":
      return { ...state, fieldErrors: action.fieldErrors, submitting: false };

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

const initialState: AppState = {
  view: "loading",
  token: null,
  openerOrigin: null,
  providers: [],
  selectedProvider: null,
  connectionId: null,
  errorCode: null,
  errorMessage: null,
  fieldErrors: {},
  submitting: false,
};

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export function App() {
  const [state, dispatch] = useReducer(reducer, {
    ...initialState,
    token: extractToken(),
    openerOrigin: extractOpenerOrigin(),
  });

  const popup = isPopup();

  // On mount: check for OAuth return params, else load providers
  useEffect(() => {
    const { connectionId, status, errorCode, errorMessage } = extractOAuthReturn();

    if (connectionId && status === "active") {
      const savedProviderKey = sessionStorage.getItem("omnidapter_provider_key") ?? "";
      sessionStorage.removeItem("omnidapter_provider_key");
      dispatch({ type: "OAUTH_RETURN_SUCCESS", connectionId, provider: savedProviderKey });
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

    if (!state.token) {
      dispatch({
        type: "LOAD_ERROR",
        code: "missing_token",
        message: "No link token provided. Please return to the application.",
      });
      return;
    }

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When entering oauth_init view, trigger the OAuth flow
  useEffect(() => {
    if (state.view !== "oauth_init" || !state.selectedProvider || !state.token) return;

    const redirectUri = new URL(window.location.href);
    redirectUri.search = "";
    redirectUri.hash = "";
    redirectUri.searchParams.set("token", state.token);

    sessionStorage.setItem("omnidapter_provider_key", state.selectedProvider.key);

    createConnection(state.token, {
      provider_key: state.selectedProvider.key,
      redirect_uri: redirectUri.toString(),
    })
      .then((result) => {
        if (result.authorization_url) {
          window.location.href = result.authorization_url;
        }
      })
      .catch((err: { code?: string; message?: string }) => {
        dispatch({
          type: "LOAD_ERROR",
          code: err.code ?? "oauth_error",
          message: err.message ?? "Failed to start OAuth flow.",
        });
      });
  }, [state.view, state.selectedProvider, state.token]);

  const handleCredentialSubmit = async (values: Record<string, string>) => {
    if (!state.token || !state.selectedProvider) return;
    dispatch({ type: "CREDENTIAL_SUBMIT_START" });
    try {
      const result = await createConnection(state.token, {
        provider_key: state.selectedProvider.key,
        credentials: values,
      });
      dispatch({ type: "CREDENTIAL_SUBMIT_SUCCESS", connectionId: result.connection_id });
    } catch (err: unknown) {
      const e = err as { code?: string; message?: string; fields?: Record<string, string> };
      dispatch({
        type: "CREDENTIAL_SUBMIT_ERROR",
        fieldErrors: e.fields ?? {},
        message: e.message ?? "Invalid credentials. Please try again.",
      });
    }
  };

  const handleBack = () => {
    dispatch({ type: "RETRY" });
  };

  switch (state.view) {
    case "loading":
      return <LoadingView />;

    case "provider_selection":
      return (
        <ProviderSelectionView
          providers={state.providers}
          onSelect={(p) => dispatch({ type: "SELECT_PROVIDER", provider: p })}
        />
      );

    case "oauth_init":
      return <OAuthInitView provider={state.selectedProvider!} />;

    case "credential_form":
      return (
        <CredentialFormView
          provider={state.selectedProvider!}
          fieldErrors={state.fieldErrors}
          submitting={state.submitting}
          onSubmit={handleCredentialSubmit}
          onBack={handleBack}
        />
      );

    case "success": {
      const redirectUri = state.token
        ? new URLSearchParams(window.location.search).get("redirect_uri")
        : null;
      return (
        <SuccessView
          connectionId={state.connectionId ?? ""}
          provider={state.selectedProvider?.key ?? ""}
          redirectUri={redirectUri}
          isPopup={popup}
          openerOrigin={state.openerOrigin}
        />
      );
    }

    case "error":
      return (
        <ErrorView
          code={state.errorCode ?? "unknown"}
          message={state.errorMessage ?? "An unexpected error occurred."}
          isPopup={popup}
          openerOrigin={state.openerOrigin}
          onRetry={
            state.errorCode && ["user_denied", "invalid_credentials"].includes(state.errorCode)
              ? () => dispatch({ type: "RETRY" })
              : undefined
          }
        />
      );

    default:
      return null;
  }
}
