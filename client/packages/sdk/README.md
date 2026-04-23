# @omnidapter/sdk

TypeScript client for the [Omnidapter](https://omnidapter.com) API.

## Installation

```bash
npm install @omnidapter/sdk
```

## Usage

```typescript
import { OmnidapterClient } from '@omnidapter/sdk';

const client = new OmnidapterClient({
  basePath: 'https://api.example.com',
  accessToken: 'omni_live_...',
});
```

### Providers

```typescript
// List all available providers
const { data: providers } = await client.providers.listProviders();
for (const provider of providers) {
  console.log(provider.key, provider.displayName);
}

// Get a specific provider
const { data: google } = await client.providers.getProvider({ providerKey: 'google' });
```

### Connections

```typescript
// List connections (optionally filter by status or provider)
const { data: connections } = await client.connections.listConnections({
  status: 'active',
  provider: 'google',
});

// Get a single connection
const { data: conn } = await client.connections.getConnection({ connectionId: 'conn_...' });

// Delete a connection
await client.connections.deleteConnection({ connectionId: 'conn_...' });
```

### Link tokens

Link tokens are short-lived tokens used to launch the Omnidapter Connect UI,
allowing an end user to authorise a new connection.

```typescript
const { data: token } = await client.linkTokens.createLinkToken({
  createLinkTokenRequest: {
    endUserId: 'user_123',
    allowedProviders: ['google', 'microsoft'],
  },
});

console.log(token.token);      // lt_...
console.log(token.connectUrl); // https://...?token=lt_...
console.log(token.expiresAt);  // Date
```

### Calendar

```typescript
// List calendars for a connection
const { data: calendars } = await client.calendar.listCalendars({ connectionId: 'conn_...' });

// List events
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

### Error handling

```typescript
try {
  await client.connections.getConnection({ connectionId: 'conn_unknown' });
} catch (e) {
  if (e instanceof Response) {
    console.log(e.status); // 404
    const body = await e.json();
  }
}
```

## Notes

- The SDK is generated from the server's OpenAPI spec via `scripts/generate_sdks.sh`.
  Run that script after pulling changes to regenerate the client code.
- Requires Node 18+.
