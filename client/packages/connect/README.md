# @omnidapter/connect

JavaScript/TypeScript library for embedding the Omnidapter calendar authorization flow in your app. Opens a centered popup that guides the user through OAuth, then fires callbacks on completion.

## Installation

```bash
npm install @omnidapter/connect
```

## How it works

1. Your backend creates a short-lived **link token** via `POST /v1/link-tokens`.
2. You pass that token to `connect.open()`.
3. The library opens a popup pointed at your Omnidapter server's Connect UI.
4. The popup communicates back to your page via `postMessage`, triggering your callbacks.
5. On success you receive a `connectionId` to store and use for API calls.

## Vanilla JS / TypeScript

```ts
import { OmnidapterConnect } from '@omnidapter/connect';

const connect = new OmnidapterConnect({
  baseUrl: 'https://your-omnidapter-server.example.com',
});

// Call from a user interaction (e.g. button click) to avoid popup blockers
button.addEventListener('click', async () => {
  const { token } = await fetch('/api/link-token').then(r => r.json());

  connect.open({
    token,
    onSuccess: ({ connectionId, provider }) => {
      console.log(`Connected ${provider} — connection ID: ${connectionId}`);
    },
    onError: ({ code, message }) => {
      console.error(`Connect error [${code}]: ${message}`);
    },
    onClose: () => {
      console.log('User closed the popup');
    },
  });
});
```

### Closing programmatically

```ts
connect.close();
```

If a popup is already open when `open()` is called again, the existing popup is focused rather than opening a second one.

## React

Import the hook from `@omnidapter/connect/react`. React 17+ is supported as a peer dependency.

```tsx
import { useOmnidapterConnect } from '@omnidapter/connect/react';

function ConnectButton() {
  const { open, close, isOpen } = useOmnidapterConnect({
    baseUrl: 'https://your-omnidapter-server.example.com',
  });

  const handleClick = async () => {
    const { token } = await fetch('/api/link-token').then(r => r.json());

    open({
      token,
      onSuccess: ({ connectionId, provider }) => {
        console.log(`Connected ${provider}: ${connectionId}`);
      },
      onError: ({ code, message }) => {
        console.error(`[${code}] ${message}`);
      },
      onClose: () => {
        console.log('Popup closed');
      },
    });
  };

  return (
    <button onClick={handleClick} disabled={isOpen}>
      {isOpen ? 'Connecting…' : 'Connect Calendar'}
    </button>
  );
}
```

The hook creates one `OmnidapterConnect` instance per component mount and cleans it up on unmount. `baseUrl` is read only on mount — pass it as a stable value.

## API

### `new OmnidapterConnect(options?)`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `baseUrl` | `string` | `https://omnidapter.heckerlabs.ai` | Base URL of your Omnidapter server |

### `connect.open(options)`

Opens (or focuses) the Connect popup.

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `token` | `string` | Yes | Link token from `POST /v1/link-tokens` |
| `onSuccess` | `(result: ConnectSuccessResult) => void` | No | Called when the connection is created |
| `onError` | `(error: ConnectErrorResult) => void` | No | Called when an error occurs in the popup |
| `onClose` | `() => void` | No | Called when the user closes the popup |
| `width` | `number` | No | Popup width in pixels (default: `520`) |
| `height` | `number` | No | Popup height in pixels (default: `640`) |

### `connect.close()`

Closes the popup and removes all event listeners.

### `ConnectSuccessResult`

```ts
{ connectionId: string; provider: string }
```

### `ConnectErrorResult`

```ts
{ code: string; message: string }
```

### `useOmnidapterConnect(options?)` (React)

Returns `{ open, close, isOpen }`. `open` and `close` have the same signatures as the class methods. `isOpen` is `true` while the popup is open.

## Error codes

| Code | Cause |
|------|-------|
| `popup_blocked` | The browser prevented the popup from opening. Ensure `open()` is called directly from a user interaction. |
| Any other code | Passed through from the Connect UI — check the `message` field for details. |

## Popup blockers

Browsers block popups that are not opened synchronously from a user gesture. Always call `connect.open()` directly inside a click handler — do not `await` anything before calling it.

## Security

Incoming `postMessage` events are validated against both the expected origin (derived from `baseUrl`) and the popup window reference, preventing spoofed messages from other tabs or origins.

## License

MIT
