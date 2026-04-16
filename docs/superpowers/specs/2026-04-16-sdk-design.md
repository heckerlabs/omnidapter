# Omnidapter SDK Design

**Date:** 2026-04-16  
**Status:** Approved

---

## Overview

Add two SDK packages to Omnidapter and improve the existing connect package:

- **`@omnidapter/connect`** — rename of `connect-sdk`; adds a React hook entry point
- **`@omnidapter/sdk`** — Fern-generated TypeScript client for the hosted API
- **`omnidapter-sdk`** — Fern-generated Python client for the hosted API

All three are published as part of the existing release workflow.

---

## 1. Package Structure

```
client/packages/
  connect/          ← renamed from connect-sdk
  sdk/              ← new, Fern-generated TypeScript

omnidapter-sdk/     ← new, Fern-generated Python (UV workspace package)

fern/               ← Fern config at repo root
  fern.config.json
  openapi/
    openapi.json    ← checked-in, updated on each release
    overrides.yml   ← operation name / grouping cleanup
  generators.yml    ← Python + TypeScript generator config
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

## 3. `@omnidapter/sdk` + `omnidapter-sdk` (Fern-generated)

### Source of truth

The hosted FastAPI app auto-generates an OpenAPI spec. A checked-in copy lives at `fern/openapi/openapi.json` and is refreshed as part of the release PR.

### Naming overrides

`fern/openapi/overrides.yml` maps FastAPI's auto-generated operation IDs to clean, resource-grouped method names:

```
client.connections.list()
client.connections.get(connection_id)
client.connections.delete(connection_id)
client.events.list(connection_id)
client.link_tokens.create()
client.api_keys.list()
client.api_keys.create()
client.api_keys.delete(key_id)
# ...all hosted routes
```

### Generated output

| Language   | Output path          | Published as       |
|------------|----------------------|--------------------|
| TypeScript | `client/packages/sdk/` | `@omnidapter/sdk` on npm |
| Python     | `omnidapter-sdk/`    | `omnidapter-sdk` on PyPI |

Both SDKs include:
- Auth (API key header) wired up by Fern
- Typed request/response models
- Typed error types
- No handwritten transport code

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

1. Version bumps across all packages:
   - `omnidapter-hosted` (Python)
   - `omnidapter-sdk` (Python)
   - `@omnidapter/connect` (npm)
   - `@omnidapter/sdk` (npm)
2. Exported `fern/openapi/openapi.json` from the hosted app
3. Fern-generated SDK code committed into `client/packages/sdk/` and `omnidapter-sdk/`

All generated diffs are reviewable in the PR before merge.

### On merge

Merging the release PR triggers:

1. Git tag + GitHub Release created
2. Docker image published to GHCR
3. `@omnidapter/connect` published to npm
4. `@omnidapter/sdk` published to npm
5. `omnidapter-sdk` published to PyPI

The publish job runs after Docker, using already-committed generated code — no generation happens at publish time.
