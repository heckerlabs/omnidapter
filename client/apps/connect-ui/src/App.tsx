import { createConnection } from "./api";
import { LoadingView } from "./views/Loading";
import { ProviderSelectionView } from "./views/ProviderSelection";
import { OAuthInitView } from "./views/OAuthInit";
import { CredentialFormView } from "./views/CredentialForm";
import { SuccessView } from "./views/Success";
import { ErrorView } from "./views/Error";
import { isPopup } from "./utils/window";
import { SESSION_STORAGE_KEY } from "./constants";
import { useAppReducer } from "./hooks/useAppReducer";
import { useAuthFlow } from "./hooks/useAuthFlow";

export function App() {
    const [state, dispatch] = useAppReducer();
    const popup = isPopup();

    useAuthFlow(state, dispatch);

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

    const handleCancel = () => {
        if (popup && window.opener && state.openerOrigin) {
            window.opener.postMessage({ type: "omnidapter:close" }, state.openerOrigin);
            window.close();
        } else if (state.redirectUri) {
            const url = new URL(state.redirectUri);
            url.searchParams.set("status", "cancelled");
            window.location.href = url.toString();
        }
    };

    switch (state.view) {
        case "loading":
            return <LoadingView />;

        case "provider_selection":
            return (
                <ProviderSelectionView
                    providers={state.providers}
                    onSelect={(p) => dispatch({ type: "SELECT_PROVIDER", provider: p })}
                    onCancel={handleCancel}
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
                    onBack={state.providers.length > 1 ? handleBack : handleCancel}
                />
            );

        case "success": {
            sessionStorage.removeItem(SESSION_STORAGE_KEY);
            const services = state.selectedProvider?.services ?? state.oauthProviderServices ?? [];
            return (
                <SuccessView
                    connectionId={state.connectionId ?? ""}
                    provider={state.selectedProvider?.key ?? state.oauthProvider ?? ""}
                    services={services}
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
                    redirectUri={state.redirectUri}
                    onRetry={
                        state.errorCode &&
                        ["user_denied", "invalid_credentials"].includes(state.errorCode)
                            ? () => dispatch({ type: "RETRY" })
                            : undefined
                    }
                />
            );

        default:
            return null;
    }
}
