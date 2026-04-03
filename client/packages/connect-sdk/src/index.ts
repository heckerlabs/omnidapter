/**
 * @omnidapter/connect — Omnidapter Connect JavaScript snippet.
 *
 * Opens the Connect page in a popup and fires callbacks when the user
 * completes, errors out, or closes the popup.
 *
 * @example
 * ```ts
 * import { OmnidapterConnect } from '@omnidapter/connect-sdk';
 *
 * const connect = new OmnidapterConnect({
 *   baseUrl: 'https://omnidapter.heckerlabs.ai',
 * });
 *
 * connect.open({
 *   token: 'lt_...',
 *   onSuccess: ({ connectionId, provider }) => console.log('Connected:', connectionId),
 *   onError: ({ code, message }) => console.error('Error:', code, message),
 *   onClose: () => console.log('Closed'),
 * });
 * ```
 */

export interface OmnidapterConnectOptions {
    /** Base URL of the Omnidapter hosted API. Defaults to the official hosted URL. */
    baseUrl?: string;
}

export interface ConnectSuccessResult {
    connectionId: string;
    provider: string;
}

export interface ConnectErrorResult {
    code: string;
    message: string;
}

export interface OpenOptions {
    /** Short-lived link token obtained from POST /v1/link-tokens. */
    token: string;
    /** Called when the connection is successfully created. */
    onSuccess?: (result: ConnectSuccessResult) => void;
    /** Called when an error occurs inside the popup. */
    onError?: (error: ConnectErrorResult) => void;
    /** Called when the user closes the popup without completing the flow. */
    onClose?: () => void;
    /** Popup window width in pixels. Defaults to 520. */
    width?: number;
    /** Popup window height in pixels. Defaults to 640. */
    height?: number;
}

// ---------------------------------------------------------------------------
// postMessage payload types (mirrors the SPA's contracts)
// ---------------------------------------------------------------------------

interface SuccessMessage {
    type: "omnidapter:success";
    connectionId: string;
    provider: string;
}

interface ErrorMessage {
    type: "omnidapter:error";
    code: string;
    message: string;
}

interface CloseMessage {
    type: "omnidapter:close";
}

type OmnidapterMessage = SuccessMessage | ErrorMessage | CloseMessage;

function isOmnidapterMessage(data: unknown): data is OmnidapterMessage {
    return (
        typeof data === "object" &&
        data !== null &&
        typeof (data as Record<string, unknown>).type === "string" &&
        ((data as Record<string, unknown>).type as string).startsWith("omnidapter:")
    );
}

// ---------------------------------------------------------------------------
// OmnidapterConnect class
// ---------------------------------------------------------------------------

const DEFAULT_BASE_URL = "https://omnidapter.heckerlabs.ai";

export class OmnidapterConnect {
    private readonly _baseUrl: string;
    private _popup: Window | null = null;
    private _pollTimer: ReturnType<typeof setInterval> | null = null;
    private _messageHandler: ((event: MessageEvent) => void) | null = null;

    constructor(options: OmnidapterConnectOptions = {}) {
        this._baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, "");
    }

    /**
     * Open the Connect popup.
     *
     * If a popup is already open, it is focused rather than opening a second one.
     */
    open(options: OpenOptions): void {
        const { token, onSuccess, onError, onClose, width = 520, height = 640 } = options;

        if (this._popup && !this._popup.closed) {
            this._popup.focus();
            return;
        }

        const connectUrl = `${this._baseUrl}?token=${encodeURIComponent(token)}&opener_origin=${encodeURIComponent(window.location.origin)}`;
        const popupFeatures = _centeredPopupFeatures(width, height);
        this._popup = window.open(connectUrl, "omnidapter_connect", popupFeatures);

        if (!this._popup) {
            // Browser blocked the popup
            onError?.({ code: "popup_blocked", message: "The popup was blocked by the browser." });
            return;
        }

        this._setupListeners(onSuccess, onError, onClose);
    }

    /** Close the popup and clean up listeners. */
    close(): void {
        this._cleanup();
        if (this._popup && !this._popup.closed) {
            this._popup.close();
        }
        this._popup = null;
    }

    // ---------------------------------------------------------------------------
    // Private helpers
    // ---------------------------------------------------------------------------

    private _setupListeners(
        onSuccess?: (r: ConnectSuccessResult) => void,
        onError?: (e: ConnectErrorResult) => void,
        onClose?: () => void
    ): void {
        // Message listener — validates origin and source to prevent spoofing
        this._messageHandler = (event: MessageEvent) => {
            if (!this._isAllowedOrigin(event.origin)) return;
            if (event.source !== this._popup) return;
            if (!isOmnidapterMessage(event.data)) return;

            const msg = event.data;
            switch (msg.type) {
                case "omnidapter:success":
                    this._cleanup();
                    onSuccess?.({ connectionId: msg.connectionId, provider: msg.provider });
                    break;
                case "omnidapter:error":
                    this._cleanup();
                    onError?.({ code: msg.code, message: msg.message });
                    break;
                case "omnidapter:close":
                    this._cleanup();
                    onClose?.();
                    break;
            }
        };

        window.addEventListener("message", this._messageHandler);

        // Poll to detect manual popup close
        this._pollTimer = setInterval(() => {
            if (this._popup?.closed) {
                this._cleanup();
                onClose?.();
            }
        }, 500);
    }

    private _cleanup(): void {
        if (this._messageHandler) {
            window.removeEventListener("message", this._messageHandler);
            this._messageHandler = null;
        }
        if (this._pollTimer !== null) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
    }

    private _isAllowedOrigin(origin: string): boolean {
        try {
            const allowed = new URL(this._baseUrl).origin;
            return origin === allowed;
        } catch {
            return false;
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _centeredPopupFeatures(width: number, height: number): string {
    const left = Math.max(0, (window.screen.width - width) / 2 + (window.screenX ?? 0));
    const top = Math.max(0, (window.screen.height - height) / 2 + (window.screenY ?? 0));
    return [
        `width=${width}`,
        `height=${height}`,
        `left=${Math.round(left)}`,
        `top=${Math.round(top)}`,
        "resizable=yes",
        "scrollbars=yes",
        "status=no",
        "toolbar=no",
        "menubar=no",
        "location=no",
    ].join(",");
}
