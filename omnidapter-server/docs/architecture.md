# Architecture

## Overview

`omnidapter-server` is a FastAPI service wrapping `omnidapter` core.

Layers:

1. Routers (`src/omnidapter_server/routers`) - HTTP interface
2. Service flows (`src/omnidapter_server/services`) - business orchestration
3. Models/stores - persistence and credential/state handling
4. Core library (`omnidapter-core`) - provider abstractions and transport

## Main Components

- `main.py`: app assembly, middleware, CORS, router registration
- `dependencies.py`: auth context, encryption service injection
- `origin_policy.py`: CORS + redirect URL policy logic
- `services/*_flows.py`: shared endpoint workflows
- `stores/credential_store.py`: encrypted token persistence
- `stores/oauth_state_store.py`: OAuth state persistence

## Data Model (high-level)

- `api_keys`
- `connections`
- `provider_configs`

## Request Lifecycle

1. Request ID middleware assigns `request_id`
2. Auth dependency resolves and validates API key
3. Router invokes service flow
4. Flow coordinates database + core library
5. Response serialized with `meta.request_id`

## Design Notes

- Server is intentionally single-tenant/global-admin for self-hosted use
- Hosted multi-tenant behavior is handled outside this app
