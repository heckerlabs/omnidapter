# Omnidapter Connect UI Specification

The **Connect UI** is a secure, specialized Single Page Application (SPA) that acts as the bridge between a host application and third-party calendar providers. It is designed to be embedded in a popup or used via direct redirection.

---

## 🏗️ Architecture Overview

The UI is a state-driven React application that handles the entire lifecycle of a connection request—from validating the initial session to finalizing the OAuth handshake or credential submission.

### 🔌 Integration Patterns

#### 1. Popup Pattern (Recommended)
The host application opens the Connect UI in a new window using `window.open()`.
*   **Trigger**: Detection of `window.opener`.
*   **Handshake**: Requires an `opener_origin` URL parameter for secure `postMessage` communication.
*   **Completion**: Sends a `postMessage` to the parent and automatically closes itself.

#### 2. Redirect Pattern
The host application redirects the user's browser to the Connect UI.
*   **Trigger**: Absence of `window.opener`.
*   **Completion**: Redirects the user back to the provided `redirect_uri` with `connection_id` and `status` appended as query parameters.

---

## 🔐 Security & Initialization

### 🎟️ Link Token Handshake
On initialization, the UI extracts a **Link Token** from the `token` URL parameter.
*   **Persistence**: The token is held in React state—it is **never** persisted to `localStorage` or `sessionStorage` to prevent session stealing.
*   **Validation**: The token is used in the `Authorization: Bearer <token>` header for all subsequent API calls.

### 🌐 Cross-Origin Security
When operating as a popup, the UI performs strict origin validation:
*   The `opener_origin` must be a valid URL (scheme + host).
*   Messages are only sent to the `window.opener` target matching this origin.

---

## 🛠️ Main Workflows

### 1. Provider Discovery
Upon valid token detection, the UI fetches available providers for the current session.
*   **Endpoint**: `GET /api/providers`
*   **Logic**:
    *   If **multiple** providers are allowed, show the `ProviderSelection` view.
    *   If **one** provider is allowed (e.g., a "reconnect" flow), skip the selection and go straight to the auth flow for that provider.
    *   If **zero** providers are found, transition to the `error` state.

### 2. OAuth2 Authorization Flow
For providers like Google and Microsoft:
*   **Trigger**: User selects an OAuth provider.
*   **Action**: Calls `POST /api/connections` to retrieve an `authorization_url`.
*   **Redirection**: Navigates the current window to the provider’s consent screen.
*   **Return**: Upon successful external auth, the backend redirects back to the Connect UI with success/error parameters in the URL.

### 3. Schema-Driven Credential Flow
For providers requiring fixed credentials (e.g., Apple, CalDAV, Sync.com):
*   **Trigger**: User selects a provider with a `credential_schema`.
*   **Action**: Dynamically generates a form based on the JSON schema provided by the backend.
*   **Fields**: Supports `text`, `password`, `email`, and `select` types with real-time validation feedback.
*   **Submission**: Sends the collected credentials to `POST /api/connections`.

---

## 📡 Communication Protocol (`postMessage`)

When in popup mode, the following messages are emitted to the `window.opener`:

### Success Message
```json
{
  "type": "omnidapter:success",
  "connectionId": "conn_123...",
  "provider": "google"
}
```

### Error Message
```json
{
  "type": "omnidapter:error",
  "code": "access_denied",
  "message": "The user denied the request."
}
```

---

## 🎨 UI Views

1.  **Loading**: Initial state while validating token and fetching providers.
2.  **ProviderSelection**: Grid of available providers with icons and names.
3.  **OAuthInit**: Temporary "Connecting..." state before redirecting to the provider.
4.  **CredentialForm**: Dynamic input form for manual credential entry.
5.  **Success**: Final confirmation screen with an optional redirect timer.
6.  **Error**: Clear error codes and messages with a "Try Again" trigger for recoverable failures (like invalid credentials).
