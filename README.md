# 🏗️ Omnidapter

**Provider-agnostic calendar integrations for Python and self-hosted APIs.**

Omnidapter is a unified integration engine that eliminates the complexity of supporting multiple calendar providers. Stop writing separate implementations for Google, Microsoft, Apple, and Zoho—Omnidapter gives you one consistent API surface and data model.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/release/python-3100/)

---

## ⚡ Main Features

- 🔄 **Unified Interface**: One model for events, calendars, and availability across all providers.
- 🔑 **OAuth Management**: Automated lifecycle for authorization flows, callbacks, and token refreshes.
- 📦 **Dual Distribution**: Use as a **Python SDK** or a standalone **REST API**.
- 🛡️ **Explicit Capability Checks**: Easily determine which features a specific provider supports.
- 💾 **Plug-and-Play Storage**: Clear separation of credential storage from provider logic.

---

## 🏛️ Architecture

```mermaid
graph TD
    UserApp(Your Application) --> CoreSDK["omnidapter-core (Python SDK)"]
    UserApp --> Server["omnidapter-server (REST API)"]
    Server --> CoreSDK
    CoreSDK --> P_Google[Google]
    CoreSDK --> P_MS[Microsoft]
    CoreSDK --> P_Apple[Apple]
    CoreSDK --> P_Caldav[CalDAV]
    CoreSDK --> P_Zoho[Zoho]
```

---

## 🧩 Project Structure

- **[`omnidapter-core`](omnidapter-core/README.md)**: The core Python library. Best if your application is Python-based and you want deep, native integration.
- **[`omnidapter-server`](omnidapter-server/docs/README.md)**: A production-ready FastAPI service that wraps the core. Best for polyglot systems or independent microservices.

---

## 🚀 60-Second Quick Start

### Python Library

```bash
pip install omnidapter
```

```python
from omnidapter import Omnidapter

omni = Omnidapter(
    credential_store=my_enc_store,
    oauth_state_store=my_redis_store,
)

# Seamlessly interact with any connection
conn = await omni.connection("google_conn_1")
calendar = conn.calendar()

# List primary calendar events
async for event in calendar.list_events("primary"):
    print(f"[{event.start}] {event.summary}")
```

### Self-Hosted API

Pull the latest stack and start services:

```bash
# Setup infrastructure (Postgres + Migration)
docker-compose -f omnidapter-server/docker-compose.yml up -d

# Bootstrap the first API key
uv run --package omnidapter-server omnidapter-bootstrap --name "local-dev"

# Call the API
curl -H "Authorization: Bearer <API_KEY>" \
  http://localhost:8000/v1/providers
```

---

## 🛠️ Supported Providers

| Provider | Status | OAuth | Recurring Events | Free/Busy |
|----------|---------|-------|------------------|-----------|
| **Google** | ✅ Production | Yes | ✅ | ✅ |
| **Microsoft** | ✅ Production | Yes | ✅ | ✅ |
| **Zoho** | ✅ Production | Yes | ✅ | ❌ |
| **Apple** | 🛰️ Beta | App Pass | ✅ | ❌ |
| **CalDAV** | 🛰️ Beta | Basic | ✅ | ❌ |

---

## 👩‍💻 Development

Omnidapter uses `uv` for package management and `poe` for task automation.

```bash
# Run local checks (format, lint, typecheck, tests)
uv run poe check

# Start development server
uv run poe server-dev
```

---

## 📜 License

MIT - See [LICENSE](LICENSE) for details.

