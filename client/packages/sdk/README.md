# @omnidapter/sdk

TypeScript client for the [Omnidapter](https://omnidapter.com) API.

Omnidapter lets you connect to your users' calendars (and other services) through a single unified API. You create a link token, send the user through the Connect UI to authorise their account, and then read their data using the connection that comes back.

## Installation

```bash
npm install @omnidapter/sdk
```

Requires Node 18+.

## Getting started

Create a client with your API key and the base URL of your Omnidapter instance:

```typescript
import { OmnidapterClient } from '@omnidapter/sdk';

const client = new OmnidapterClient({
  basePath: 'https://api.example.com',
  accessToken: 'omni_live_...',
});
```

All methods are async and return a response object. The actual payload is on `.data` — you can destructure it directly:

```typescript
const { data: providers } = await client.providers.listProviders();
```

---

## Providers

Providers are the services Omnidapter can connect to (e.g. Google, Microsoft). You typically list them once to populate a picker in your UI.

```typescript
const { data: providers } = await client.providers.listProviders();
for (const provider of providers) {
  console.log(provider.key, provider.displayName);
}

// Fetch a single provider by its key
const { data: google } = await client.providers.getProvider({ providerKey: 'google' });
console.log(google.displayName);
```

---

## Connections

A connection represents an authorised link between one of your end users and a provider. Once a user completes the Connect flow, their connection appears here.

```typescript
// List all connections, optionally filtering by status or provider
const { data: connections } = await client.connections.listConnections({
  status: 'active',
  provider: 'google',
});
for (const conn of connections) {
  console.log(conn.id, conn.providerKey, conn.status);
}

// Fetch a single connection
const { data: conn } = await client.connections.getConnection({ connectionId: 'conn_...' });
console.log(conn.status);

// Revoke a connection — this also invalidates any stored credentials
await client.connections.deleteConnection({ connectionId: 'conn_...' });
```

---

## Link tokens

A link token is a short-lived, single-use token that grants an end user access to the Connect UI. Generate one server-side, pass it to your frontend, and redirect the user to `connectUrl`. Omnidapter will handle the OAuth flow and create a connection on success.

```typescript
const { data: token } = await client.linkTokens.createLinkToken({
  createLinkTokenRequest: {
    endUserId: 'user_123',                        // your internal user ID
    allowedProviders: ['google', 'microsoft'],    // restrict which providers are shown
  },
});

console.log(token.token);      // lt_... — pass this to your frontend
console.log(token.connectUrl); // redirect the user here to start the Connect flow
console.log(token.expiresAt);  // Date — tokens are short-lived, generate them on demand
```

---

## Calendar

Once a user has a connection, you can read their calendar data. All calendar operations require a `connectionId`.

```typescript
// List the calendars available on a connection
const { data: calendars } = await client.calendar.listCalendars({ connectionId: 'conn_...' });
for (const cal of calendars) {
  console.log(cal.id, cal.name);
}

// List events within a time range across a specific calendar
const { data: events } = await client.calendar.listEvents({
  connectionId: 'conn_...',
  calendarId: 'cal_...',
  start: new Date('2026-04-01T00:00:00Z'),
  end: new Date('2026-04-30T23:59:59Z'),
});
for (const event of events) {
  console.log(event.id, event.title, event.start);
}
```

---

## Error handling

The SDK throws the raw `Response` object for any non-2xx reply. You can inspect the status and parse the body to handle errors appropriately.

```typescript
try {
  await client.connections.getConnection({ connectionId: 'conn_unknown' });
} catch (e) {
  if (e instanceof Response) {
    console.log(e.status);       // e.g. 404
    const body = await e.json(); // JSON error body from the server
  }
}
```

---

## Notes

- The SDK is generated from the server's OpenAPI spec via `scripts/generate_sdks.sh`.
  Run that script after pulling changes to regenerate the client code.
