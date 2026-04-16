/**
 * Unit tests for the OmnidapterConnect JS snippet.
 *
 * Tests run in jsdom via Vitest.
 */
import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { OmnidapterConnect } from "./index";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockPopup(closed = false) {
    return {
        closed,
        focus: vi.fn(),
        close: vi.fn(),
        postMessage: vi.fn(),
    };
}

// ---------------------------------------------------------------------------
// Constructor
// ---------------------------------------------------------------------------

describe("OmnidapterConnect constructor", () => {
    it("uses default baseUrl", () => {
        const c = new OmnidapterConnect();
        // Access private via type cast
        expect((c as unknown as { _baseUrl: string })._baseUrl).toBe(
            "https://app.omnidapter.io"
        );
    });

    it("uses provided baseUrl (strips trailing slash)", () => {
        const c = new OmnidapterConnect({ baseUrl: "https://custom.example.com/" });
        expect((c as unknown as { _baseUrl: string })._baseUrl).toBe("https://custom.example.com");
    });
});

// ---------------------------------------------------------------------------
// open() — popup blocked
// ---------------------------------------------------------------------------

describe("open() — popup blocked", () => {
    it("calls onError with popup_blocked when window.open returns null", () => {
        const c = new OmnidapterConnect({ baseUrl: "https://app.omnidapter.io" });
        const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
        const onError = vi.fn();

        c.open({ token: "lt_abc", onError });

        expect(openSpy).toHaveBeenCalledOnce();
        expect(onError).toHaveBeenCalledWith({
            code: "popup_blocked",
            message: expect.stringContaining("blocked"),
        });

        openSpy.mockRestore();
    });
});

// ---------------------------------------------------------------------------
// open() — popup opened successfully
// ---------------------------------------------------------------------------

describe("open() — popup opened", () => {
    let openSpy: MockInstance;
    let mockPopup: ReturnType<typeof createMockPopup>;
    let addEventListenerSpy: MockInstance;
    let removeEventListenerSpy: MockInstance;

    beforeEach(() => {
        mockPopup = createMockPopup();
        openSpy = vi.spyOn(window, "open").mockReturnValue(mockPopup as unknown as Window);
        addEventListenerSpy = vi.spyOn(window, "addEventListener");
        removeEventListenerSpy = vi.spyOn(window, "removeEventListener");
        vi.useFakeTimers();
    });

    afterEach(() => {
        openSpy.mockRestore();
        addEventListenerSpy.mockRestore();
        removeEventListenerSpy.mockRestore();
        vi.useRealTimers();
    });

    it("opens popup with correct URL including token", () => {
        const c = new OmnidapterConnect({ baseUrl: "https://app.omnidapter.io" });
        c.open({ token: "lt_testtoken" });

        expect(openSpy).toHaveBeenCalledWith(
            expect.stringContaining("lt_testtoken"),
            "omnidapter_connect",
            expect.any(String)
        );
    });

    it("adds a message event listener", () => {
        const c = new OmnidapterConnect({ baseUrl: "https://app.omnidapter.io" });
        c.open({ token: "lt_x" });
        expect(addEventListenerSpy).toHaveBeenCalledWith("message", expect.any(Function));
    });

    it("fires onSuccess when receiving success postMessage from correct origin", () => {
        const onSuccess = vi.fn();
        const c = new OmnidapterConnect({ baseUrl: "https://app.omnidapter.io" });
        c.open({ token: "lt_x", onSuccess });

        // Extract the message listener that was registered
        const listener = addEventListenerSpy.mock.calls.find(
            ([type]) => type === "message"
        )?.[1] as EventListener;
        expect(listener).toBeDefined();

        // Simulate postMessage from the correct origin and source (the popup window)
        listener(
            new MessageEvent("message", {
                origin: "https://app.omnidapter.io",
                source: mockPopup as unknown as Window,
                data: {
                    type: "omnidapter:success",
                    connectionId: "conn_123",
                    provider: "google",
                },
            })
        );

        expect(onSuccess).toHaveBeenCalledWith({ connectionId: "conn_123", provider: "google" });
    });

    it("ignores postMessage from wrong origin", () => {
        const onSuccess = vi.fn();
        const c = new OmnidapterConnect({ baseUrl: "https://app.omnidapter.io" });
        c.open({ token: "lt_x", onSuccess });

        const listener = addEventListenerSpy.mock.calls.find(
            ([type]) => type === "message"
        )?.[1] as EventListener;

        listener(
            new MessageEvent("message", {
                origin: "https://evil.attacker.com",
                data: { type: "omnidapter:success", connectionId: "conn_hack", provider: "google" },
            })
        );

        expect(onSuccess).not.toHaveBeenCalled();
    });

    it("fires onError when receiving error postMessage", () => {
        const onError = vi.fn();
        const c = new OmnidapterConnect({ baseUrl: "https://app.omnidapter.io" });
        c.open({ token: "lt_x", onError });

        const listener = addEventListenerSpy.mock.calls.find(
            ([type]) => type === "message"
        )?.[1] as EventListener;

        listener(
            new MessageEvent("message", {
                origin: "https://app.omnidapter.io",
                source: mockPopup as unknown as Window,
                data: {
                    type: "omnidapter:error",
                    code: "user_denied",
                    message: "The user denied access.",
                },
            })
        );

        expect(onError).toHaveBeenCalledWith({
            code: "user_denied",
            message: "The user denied access.",
        });
    });

    it("fires onClose when popup is manually closed", () => {
        const onClose = vi.fn();
        const c = new OmnidapterConnect({ baseUrl: "https://app.omnidapter.io" });
        c.open({ token: "lt_x", onClose });

        // Simulate user closing the popup
        mockPopup.closed = true;
        vi.advanceTimersByTime(600);

        expect(onClose).toHaveBeenCalledOnce();
    });

    it("focuses existing popup instead of opening a second one", () => {
        const c = new OmnidapterConnect({ baseUrl: "https://app.omnidapter.io" });
        c.open({ token: "lt_x" });
        c.open({ token: "lt_x" }); // second call

        expect(openSpy).toHaveBeenCalledOnce(); // only one popup opened
        expect(mockPopup.focus).toHaveBeenCalledOnce();
    });

    it("removes event listener after success", () => {
        const onSuccess = vi.fn();
        const c = new OmnidapterConnect({ baseUrl: "https://app.omnidapter.io" });
        c.open({ token: "lt_x", onSuccess });

        const listener = addEventListenerSpy.mock.calls.find(
            ([type]) => type === "message"
        )?.[1] as EventListener;

        listener(
            new MessageEvent("message", {
                origin: "https://app.omnidapter.io",
                source: mockPopup as unknown as Window,
                data: { type: "omnidapter:success", connectionId: "conn_abc", provider: "google" },
            })
        );

        expect(removeEventListenerSpy).toHaveBeenCalledWith("message", expect.any(Function));
    });
});

// ---------------------------------------------------------------------------
// close()
// ---------------------------------------------------------------------------

describe("close()", () => {
    it("closes the popup window", () => {
        const mockPopup = createMockPopup();
        vi.spyOn(window, "open").mockReturnValue(mockPopup as unknown as Window);
        vi.useFakeTimers();

        const c = new OmnidapterConnect({ baseUrl: "https://app.omnidapter.io" });
        c.open({ token: "lt_x" });
        c.close();

        expect(mockPopup.close).toHaveBeenCalled();
        vi.useRealTimers();
    });
});
