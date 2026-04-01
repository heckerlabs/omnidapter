# Omnidapter Core: Functional Specification

The **Omnidapter Core** is a Python library designed to provide a unified, provider-agnostic interface for interacting with various third-party services (starting with Calendars). It handles the heavy lifting of authentication, data mapping, and API communication, allowing developers to build integrations once and run them against multiple providers like Google, Microsoft, Apple, and more.

**License**: MIT (Open Source)

---

## 1. Core Architecture

### 1.1 The Engine (`Omnidapter`)
The central entry point for the library. It orchestrates the lifecycle of connections and manages global configuration.
*   **Provider Registration**: Maintains a registry of available service providers (e.g., Google, Microsoft).
*   **Connection Retrieval**: Fetches active `Connection` objects by ID, automatically resolving credentials and injecting shared resources like HTTP clients.
*   **Auto-Configuration**: Optionally auto-registers built-in providers by detecting relevant environment variables (e.g., `GOOGLE_CLIENT_ID`).

### 1.2 The Registry (`ProviderRegistry`)
A catalog of all supported providers.
*   **Dynamic Registration**: Allows third-party or custom providers to be registered at runtime.
*   **Metadata Inspection**: Provides human-readable names and capability lists for each registered provider.

### 1.3 The Connection (`Connection`)
Represents a specific, authorized link to a user's account at a provider.
*   **Service Access**: Acts as a gateway to service-specific interfaces (e.g., `conn.calendar()`).
*   **Credential Lifecycle**: Handles automatic token refreshing and credential resolution before making API calls.
*   **Context Injection**: Ensures that every request is associated with the correct connection ID and uses configured retry policies.

---

## 2. Authentication & Authorization

### 2.1 OAuth 2.0 Flow (`OAuthHelper`)
A robust implementation of the OAuth 2.0 Authorization Code Flow, enriched with security and developer experience features.
*   **PKCE Support**: Automatically generates and verifies "Proof Key for Code Exchange" (PKCE) challenges for providers that support it.
*   **State Management**: Securely persists and verifies the `state` parameter to prevent CSRF attacks.
*   **Customization**: Supports overriding default scopes and passing extra provider-specific authorization parameters (e.g., `prompt=consent`).
*   **Safety Checks**: Strictly validates connection IDs, providers, and redirect URIs during the completion phase.

### 2.2 Pluggable Storage (`Stores`)
To remain infrastructure-agnostic, Omnidapter uses abstract storage interfaces.
*   **CredentialStore**: Persists sensitive tokens (Access/Refresh) and configuration.
*   **OAuthStateStore**: Temporarily holds pending OAuth session data during the redirect loop.
*   **Reference Implementations**: Includes thread-safe in-memory stores for testing and lightweight use.

---

## 3. Provider Ecosystem

Omnidapter unifies diverse API signatures into a single interface.

| Provider | Auth Type | Native Protocol | Notes |
| :--- | :--- | :--- | :--- |
| **Google** | OAuth2 | REST | Full Meet conference support. |
| **Microsoft** | OAuth2 | Graph | Supports both Personal and Work/School accounts. |
| **Zoho** | OAuth2 | REST | Regional data center support. |
| **Apple** | Basic (App-pw) | CalDAV | Hardcoded iCloud discovery. |
| **Generic CalDAV**| Basic | CalDAV | Flexible URL configuration for Nextcloud/Fastmail. |

---

## 4. Service: Calendar

The Calendar service is the primary functional area of Omnidapter Core.

### 4.1 Data Homogenization (`Mappers`)
Omnidapter maps complex nested provider objects into clean, flat models.
*   **`CalendarEvent`**: A unified model for events. Fields like `summary`, `start`, `end`, and `attendees` are mapped predictably across all providers.
*   **Flexibility**: Original provider data is preserved in a `provider_data` dictionary for advanced use cases where raw access is needed.
*   **Recurrence**: Full support for iCal recurrence rules (RRULE). Mappers handle the transformation between provider-specific recurrence formats and standard iCal strings.

### 4.2 Core Capabilities
*   **Event CRUD**: Create, read, update, and delete events with a single method call regardless of the provider.
*   **Calendar Management**: List available calendars, get details, and manage secondary calendars (where supported).
*   **Availability**: Query free/busy slots across multiple calendars.
*   **Timezones**: Sophisticated handling of floating times vs. fixed offsets, ensuring events appear correctly in local calendars.

---

## 5. Reliability & Performance

### 5.1 Resilience
*   **Retry Policies**: Configurable retry logic with support for "no-retry" and "exponential backoff" strategies.
*   **Rate Limit Awareness**: Intelligently parses provider headers (e.g., `Retry-After`) and raises structured `RateLimitError` exceptions with recommended wait times.

### 5.2 Efficiency
*   **Connection Pooling**: Supports sharing a single `httpx.AsyncClient` across all connections and services to optimize resource usage and performance.

---

## 6. Error Handling

Omnidapter uses a granular, hierarchical exception system to help developers react correctly to failures.

*   **`AuthError`**: Base for all authentication issues (e.g., `TokenRefreshError`, `OAuthStateError`).
*   **`ProviderAPIError`**: Represents a failed request to the third-party API. Includes status codes, response bodies, and correlation IDs for debugging.
*   **`TransportError`**: Network-level failures (timeouts, DNS issues).
*   **`UnsupportedCapabilityError`**: Raised when a requested feature (e.g., recurring event creation) is not supported by the underlying provider.
