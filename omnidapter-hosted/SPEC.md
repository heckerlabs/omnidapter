# Omnidapter Hosted: Functional Specification

**Omnidapter Hosted** is the managed, private SaaS version of the Omnidapter platform. It builds upon the open-source `core` and `server` components, adding production-grade identity management, multi-tenancy, and a developer dashboard.

**License**: Private (SaaS)

---

## 1. SaaS Infrastructure & IAM

Omnidapter Hosted introduces a layered identity model to manage human users and their organizations.

### 1.1 Tenants & Plans
A **Tenant** is the primary customer entity in the SaaS.
*   **Scoped Resources**: All connections, provider configurations, and API keys belong to a specific tenant.
*   **Plans**: Supports tiered access levels (e.g., `FREE`, `PRO`), which can be used to gate features or usage limits.

### 1.2 Users & Memberships
*   **HostedUser**: Represents a human developer or administrator.
*   **HostedMembership**: A many-to-many relationship linking users to tenants. 
*   **Roles**: Supports Role-Based Access Control (RBAC) with roles like `OWNER` and `MEMBER`.

---

## 2. Developer Dashboard API

The `/v1/dashboard` endpoints provide self-service capabilities for developers using the hosted platform.

### 2.1 Profile & Authentication
*   **JWT Auth**: Uses JSON Web Tokens (JWT) for dashboard sessions. Tokens include claims for the current `user_id`, `tenant_id`, and `role`.
*   **Profile Management**: Endpoints to view and update user details (name, email).

### 2.2 Tenant Management
*   **Settings**: View tenant-wide configurations and current subscription status.
*   **Team Management**: (Future) Inviting and managing members within a tenant.

### 2.3 API Key Management
Allows developers to generate keys for authenticating their own applications against the Omnidapter Hosted API.
*   **Key Format**: Uses a secure prefix-based format (e.g., `omni_live_...`).
*   **Dashboard Creation**: Developers can create nameable keys, which are hashed and stored securely.

---

## 3. Hosted Service API

The Hosted API mirrors the Open Source `omnidapter-server` API but with added SaaS-level enforcement.

### 3.1 Connection Proxying
*   **Enhanced Isolation**: Every connection operation (CRUD) is strictly validated against the authenticated tenant.
*   **Status Visibility**: Comprehensive tracking of connection health, including `last_used_at` and provider-specific error codes, forwarded to the dashboard.

### 3.2 Calendar & Data Proxy
*   **Rate Limit Buffering**: Adds a layer of protection and monitoring around third-party API rate limits.
*   **Usage Billing**: Infrastructure for recording and reporting usage volume per tenant.
*   **Unified Access**: Seamlessly bridges multiple providers (Google, MS, Apple) through a single hosted endpoint.

---

## 4. Connect UI Support

Omnidapter Hosted provides specialized support for the **Connect UI** (the embeddable auth flow).
*   **Link Tokens (Hosted)**: Generates secure, short-lived tokens specifically for the hosted environment, ensuring that end-users are correctly associated with the developer's tenant.
*   **Branding & Customization**: (Informed by Dash) Potential for tenant-specific styling and configuration of the connect flow.

---

## 5. Security & Isolation

*   **Prefix-based Key Verification**: Uses hashed lookup for API keys with human-readable prefixes for easier management and rotation.
*   **Data Sovereignty**: Ensures that credentials and user data are strictly isolated between tenants at the database level using tenant IDs on all sensitive tables.
