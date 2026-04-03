import { useEffect, useReducer, useRef } from "react";
import { createSession, listProviders, createConnection } from "./api";
import { LoadingView } from "./views/Loading";
import { ProviderSelectionView } from "./views/ProviderSelection";
import { OAuthInitView } from "./views/OAuthInit";
import { CredentialFormView } from "./views/CredentialForm";
import { SuccessView } from "./views/Success";
import { ErrorView } from "./views/Error";
import type { AppState, Provider } from "./types";

// ---------------------------------------------------------------------------
// URL parameter extraction helpers
// ---------------------------------------------------------------------------

// The bootstrap lt_ token arrives here only to be immediately exchanged.
// After exchange it is removed from the URL and the cs_ session token lives
// in memory (+ sessionStorage for OAuth round-trip survival) only.
function extractBootstrapToken(): string | null {
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

function isPopup(): boolean {
  try {
    return window.opener !== null && window.opener !== window;
  } catch {
    return false;
  }
}

function isInIframe(): boolean {
  try {
    return window !== window.top;
  } catch {
    return true;
  }
}

// ---------------------------------------------------------------------------
// State reducer
// ---------------------------------------------------------------------------

type Action =
  | { type: "SESSION_READY"; token: string; redirectUri: string | null }
  | { type: "PROVIDERS_LOADED"; providers: Provider[] }
  | { type: "PROVIDERS_EMPTY" }
  | { type: "LOAD_ERROR"; code: string; message: string }
  | { type: "SELECT_PROVIDER"; provider: Provider }
  | { type: "OAUTH_REDIRECT_STARTED" }
  | { type: "OAUTH_RETURN_SUCCESS"; connectionId: string; provider: string; redirectUri: string | null; openerOrigin: string | null }
  | { type: "OAUTH_RETURN_ERROR"; code: string; message: string }
  | { type: "CREDENTIAL_SUBMIT_START" }
  | { type: "CREDENTIAL_SUBMIT_SUCCESS"; connectionId: string }
  | { type: "CREDENTIAL_SUBMIT_ERROR"; fieldErrors: Record<string, string>; message: string }
  | { type: "RETRY" };

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "SESSION_READY":
      // Bootstrap token has been exchanged; store session token and redirect_uri
      // from the link token. Provider loading triggers on token change.
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
      return {
        ...state,
        view: "success",
        connectionId: action.connectionId,
        oauthProvider: action.provider,
        redirectUri: action.redirectUri ?? state.redirectUri,
        openerOrigin: action.openerOrigin ?? state.openerOrigin,
      };

    case "OAUTH_RETURN_ERROR":
      return { ...state, view: "error", errorCode: action.code, errorMessage: action.message };

    case "CREDENTIAL_SUBMIT_START":
      return { ...state, fieldErrors: {}, formError: null, submitting: true };

    case "CREDENTIAL_SUBMIT_SUCCESS":
      return { ...state, view: "success", connectionId: action.connectionId, submitting: false };

    case "CREDENTIAL_SUBMIT_ERROR":
      return { ...state, fieldErrors: action.fieldErrors, formError: action.message, submitting: false };

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
  redirectUri: null,
  providers: [],
  selectedProvider: null,
  oauthProvider: null,
  connectionId: null,
  errorCode: null,
  errorMessage: null,
  fieldErrors: {},
  formError: null,
  submitting: false,
};

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

const _SESSION_STORAGE_KEY = "omnidapter_session";

export function App() {
  const [state, dispatch] = useReducer(reducer, {
    ...initialState,
    // token starts null; the mount effect either restores from sessionStorage
    // (OAuth return) or exchanges the bootstrap token for a session token.
    token: null,
    openerOrigin: extractOpenerOrigin(),
  });

  const popup = isPopup();

  // Guard against React StrictMode double-invocation: the first run cleans the
  // token from the URL, so a second run would find no token and error.
  const bootstrapRan = useRef(false);

  // On mount: handle OAuth return or exchange the bootstrap token.
  useEffect(() => {
    if (bootstrapRan.current) return;
    bootstrapRan.current = true;
    const { connectionId, errorCode, errorMessage } = extractOAuthReturn();

    // --- Embed OAuth popup return path ---
    // When Connect UI is in an iframe, OAuth opens in a popup to avoid provider
    // iframe restrictions.  On return the popup postMessages the result to the
    // iframe (window.opener) and closes itself.
    if (connectionId && !errorCode && window.opener && localStorage.getItem("omnidapter_embed_oauth") === "true") {
      localStorage.removeItem("omnidapter_embed_oauth");
      const opener = window.opener as Window;
      // Read saved context from the iframe's sessionStorage (same-origin access)
      const savedProviderKey = opener.sessionStorage.getItem("omnidapter_provider_key") ?? "";
      const savedRedirectUri = opener.sessionStorage.getItem("omnidapter_redirect_uri");
      opener.postMessage(
        { type: "omnidapter:oauth_complete", connectionId, provider: savedProviderKey, redirectUri: savedRedirectUri },
        window.location.origin
      );
      window.close();
      return;
    }

    // --- OAuth return path ---
    if (connectionId && !errorCode) {
      const savedProviderKey = sessionStorage.getItem("omnidapter_provider_key") ?? "";
      const savedRedirectUri = sessionStorage.getItem("omnidapter_redirect_uri");
      const savedOpenerOrigin = sessionStorage.getItem("omnidapter_opener_origin");
      sessionStorage.removeItem("omnidapter_provider_key");
      sessionStorage.removeItem("omnidapter_redirect_uri");
      sessionStorage.removeItem("omnidapter_opener_origin");
      // Session token was stored before the OAuth redirect; restore it now.
      const savedSession = sessionStorage.getItem(_SESSION_STORAGE_KEY);
      if (savedSession) {
        dispatch({ type: "SESSION_READY", token: savedSession, redirectUri: savedRedirectUri });
      }
      dispatch({ type: "OAUTH_RETURN_SUCCESS", connectionId, provider: savedProviderKey, redirectUri: savedRedirectUri, openerOrigin: savedOpenerOrigin });
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

    // --- Fresh load path: exchange the bootstrap lt_ token ---
    const bootstrapToken = extractBootstrapToken();
    if (!bootstrapToken) {
      dispatch({
        type: "LOAD_ERROR",
        code: "missing_token",
        message: "No link token provided. Please return to the application.",
      });
      return;
    }

    // Remove the bootstrap token from the URL immediately so it never sits in
    // browser history or gets captured by referrer headers.
    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete("token");
    window.history.replaceState({}, "", cleanUrl.toString());

    createSession(bootstrapToken)
      .then(({ sessionToken, redirectUri }) => {
        // Hold the session token in sessionStorage so it survives the OAuth
        // redirect round-trip (page navigates away and back).
        sessionStorage.setItem(_SESSION_STORAGE_KEY, sessionToken);
        if (redirectUri) {
          sessionStorage.setItem("omnidapter_redirect_uri", redirectUri);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Once a session token is available, load providers.
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
  }, [state.token, state.view]);

  // When entering oauth_init view, trigger the OAuth flow
  useEffect(() => {
    if (state.view !== "oauth_init" || !state.selectedProvider || !state.token) return;

    // The redirect_uri points back to /connect with NO token in the URL.
    // The session token will be read from sessionStorage on return.
    const redirectUri = new URL(window.location.href);
    redirectUri.search = "";
    redirectUri.hash = "";

    sessionStorage.setItem("omnidapter_provider_key", state.selectedProvider.key);
    if (state.openerOrigin) {
      sessionStorage.setItem("omnidapter_opener_origin", state.openerOrigin);
    }

    createConnection(state.token, {
      provider_key: state.selectedProvider.key,
      redirect_uri: redirectUri.toString(),
    })
      .then((result) => {
        if (result.authorization_url) {
          if (isInIframe()) {
            // OAuth providers block their pages from loading inside iframes.
            // Open the authorization URL in a popup instead; the popup will
            // postMessage the result back to this iframe on return.
            localStorage.setItem("omnidapter_embed_oauth", "true");
            const w = 520, h = 640;
            const left = Math.round(Math.max(0, (screen.width - w) / 2 + (screenX ?? 0)));
            const top = Math.round(Math.max(0, (screen.height - h) / 2 + (screenY ?? 0)));
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
  }, [state.view, state.selectedProvider, state.token]);

  // When in an iframe, receive the OAuth result from the popup that was opened
  // to avoid provider iframe restrictions (see oauth_init effect above).
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

      // Clean up sessionStorage now that the OAuth round-trip is done
      const savedSession = sessionStorage.getItem(_SESSION_STORAGE_KEY);
      const savedRedirectUri = sessionStorage.getItem("omnidapter_redirect_uri");
      sessionStorage.removeItem("omnidapter_provider_key");
      sessionStorage.removeItem("omnidapter_redirect_uri");
      sessionStorage.removeItem("omnidapter_opener_origin");

      if (savedSession) {
        dispatch({ type: "SESSION_READY", token: savedSession, redirectUri: data.redirectUri ?? savedRedirectUri });
      }
      dispatch({
        type: "OAUTH_RETURN_SUCCESS",
        connectionId: data.connectionId ?? "",
        provider: data.provider ?? "",
        redirectUri: data.redirectUri ?? savedRedirectUri,
        openerOrigin: null,
      });
    };

    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

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
      // Token/session errors should show the error view, not the form
      if (e.code === "session_expired" || e.code === "unauthenticated") {
        dispatch({
          type: "LOAD_ERROR",
          code: e.code,
          message: e.message ?? "Session expired. Please try again.",
        });
      } else {
        dispatch({
          type: "CREDENTIAL_SUBMIT_ERROR",
          fieldErrors: e.fields ?? {},
          message: e.message ?? "Invalid credentials. Please try again.",
        });
      }
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
          formError={state.formError}
          submitting={state.submitting}
          onSubmit={handleCredentialSubmit}
          onBack={handleBack}
        />
      );

    case "success": {
      sessionStorage.removeItem(_SESSION_STORAGE_KEY);
      return (
        <SuccessView
          connectionId={state.connectionId ?? ""}
          provider={state.selectedProvider?.key ?? state.oauthProvider ?? ""}
          redirectUri={state.redirectUri}
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
