# Omnidapter SDK Design

**Date:** 2026-04-16  
**Status:** Approved

---

## Overview

Add two SDK packages to Omnidapter and improve the existing connect package:

- **`@omnidapter/connect`** — rename of `connect-sdk`; adds a React hook entry point
- **`@omnidapter/sdk`** — OpenAPI Generator TypeScript client for the server API
- **`omnidapter-sdk`** — OpenAPI Generator Python client for the server API

All three are published as part of the release workflow. `omnidapter-hosted` is not released publicly — it is a private SaaS component that will eventually live in its own separate repository.

---

## 1. Package Structure

```
client/packages/
  connect/          ← renamed from connect-sdk
  sdk/              ← new, OpenAPI Generator TypeScript

omnidapter-sdk/     ← new, OpenAPI Generator Python (UV workspace package)

openapi/
  openapi.json      ← checked-in, regenerated on each release
scripts/
  generate_sdks.sh  ← exports spec + runs OpenAPI Generator via Docker
  export_openapi.py ← exports filtered FastAPI spec to openapi/openapi.json
```

NPM org: `@heckerlabs` → `@omnidapter`. Requires `@omnidapter` org on npm.  
Python package name on PyPI: `omnidapter-sdk`.

---

## 2. `@omnidapter/connect`

**Changes from current `connect-sdk`:**

- Rename directory `client/packages/connect-sdk/` → `client/packages/connect/`
- Update package name to `@omnidapter/connect`
- The existing `OmnidapterConnect` class is unchanged

**New: React hook entry point**

Add `src/react.ts` as a separate subpath export so React is not pulled in for vanilla JS users:

```typescript
// Vanilla JS (unchanged)
import { OmnidapterConnect } from '@omnidapter/connect'

// React users
import { useOmnidapterConnect } from '@omnidapter/connect/react'
```

The hook signature:

```typescript
function useOmnidapterConnect(options?: OmnidapterConnectOptions): {
  open: (options: OpenOptions) => void;
  close: () => void;
  isOpen: boolean;
}
```

Behavior:
- Creates one `OmnidapterConnect` instance per mount
- Tracks popup open state via `isOpen`
- Cleans up (closes popup, removes listeners) on unmount
- React is a peer dependency — not bundled

---

## 3. `@omnidapter/sdk` + `omnidapter-sdk` (OpenAPI Generator)

### Source of truth

`omnidapter-server` FastAPI routes include explicit `operation_id` and `response_model` on every endpoint. `scripts/export_openapi.py` exports a filtered spec to `openapi/openapi.json` (excluding `/connect/`, `/oauth/`, `/health`). `scripts/generate_sdks.sh` runs OpenAPI Generator via Docker to produce both SDKs.

### Method naming

Clean method names come from explicit `operation_id` on every FastAPI route (e.g. `list_connections`, `create_link_token`). No overrides file needed.

### Generated output

| Language   | Output path          | Published as       |
|------------|----------------------|--------------------|
| TypeScript | `client/packages/sdk/src/` | `@omnidapter/sdk` on npm |
| Python     | `omnidapter-sdk/omnidapter_sdk/` | `omnidapter-sdk` on PyPI |

Both SDKs include:
- Auth (Bearer token) wired up via handwritten `OmnidapterClient` wrapper
- Typed request/response models (from FastAPI `response_model` schemas)
- Generated API classes grouped by resource

### Usage examples

**TypeScript:**
```typescript
import { OmnidapterClient } from '@omnidapter/sdk'

const client = new OmnidapterClient({ apiKey: 'omni_live_...' })
const connections = await client.connections.list()
const token = await client.linkTokens.create({ external_user_id: 'user_123' })
```

**Python:**
```python
from omnidapter_sdk import OmnidapterClient

client = OmnidapterClient(api_key="omni_live_...")
connections = await client.connections.list()
token = await client.link_tokens.create(external_user_id="user_123")
```

---

## 4. Release Workflow

### Release PR

The release PR (same trigger as today) includes:

1. Version bumps for the three public packages:
   - `omnidapter-sdk` (Python)
   - `@omnidapter/connect` (npm)
   - `@omnidapter/sdk` (npm)
2. Regenerated `openapi/openapi.json` committed (source of truth for SDK generation)

All generated diffs are reviewable in the PR before merge.

### On merge

Merging the release PR triggers:

1. Git tag + GitHub Release created
2. `@omnidapter/connect` published to npm
3. `@omnidapter/sdk` published to npm
4. `omnidapter-sdk` published to PyPI

Publishing uses already-committed generated code — no generation happens at publish time. `omnidapter-hosted` is not part of this workflow.
