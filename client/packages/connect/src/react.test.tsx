import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { OmnidapterConnect } from "./index";
import { useOmnidapterConnect } from "./react";

vi.mock("./index");

describe("useOmnidapterConnect", () => {
    let mockOpen: ReturnType<typeof vi.fn>;
    let mockClose: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        mockOpen = vi.fn();
        mockClose = vi.fn();
        vi.mocked(OmnidapterConnect).mockImplementation(
            () => ({ open: mockOpen, close: mockClose }) as unknown as OmnidapterConnect
        );
    });

    it("starts with isOpen false", () => {
        const { result } = renderHook(() => useOmnidapterConnect());
        expect(result.current.isOpen).toBe(false);
    });

    it("sets isOpen true when open() is called", () => {
        const { result } = renderHook(() => useOmnidapterConnect());
        act(() => {
            result.current.open({ token: "lt_test" });
        });
        expect(result.current.isOpen).toBe(true);
        expect(mockOpen).toHaveBeenCalledOnce();
    });

    it("sets isOpen false when wrapped onSuccess fires", () => {
        const onSuccess = vi.fn();
        const { result } = renderHook(() => useOmnidapterConnect());
        act(() => {
            result.current.open({ token: "lt_test", onSuccess });
        });
        const wrappedOptions = mockOpen.mock.calls[0][0];
        act(() => {
            wrappedOptions.onSuccess({ connectionId: "conn_123", provider: "google" });
        });
        expect(result.current.isOpen).toBe(false);
        expect(onSuccess).toHaveBeenCalledWith({ connectionId: "conn_123", provider: "google" });
    });

    it("sets isOpen false when wrapped onError fires", () => {
        const onError = vi.fn();
        const { result } = renderHook(() => useOmnidapterConnect());
        act(() => {
            result.current.open({ token: "lt_test", onError });
        });
        const wrappedOptions = mockOpen.mock.calls[0][0];
        act(() => {
            wrappedOptions.onError({ code: "user_denied", message: "denied" });
        });
        expect(result.current.isOpen).toBe(false);
        expect(onError).toHaveBeenCalledWith({ code: "user_denied", message: "denied" });
    });

    it("sets isOpen false when wrapped onClose fires", () => {
        const onClose = vi.fn();
        const { result } = renderHook(() => useOmnidapterConnect());
        act(() => {
            result.current.open({ token: "lt_test", onClose });
        });
        const wrappedOptions = mockOpen.mock.calls[0][0];
        act(() => {
            wrappedOptions.onClose();
        });
        expect(result.current.isOpen).toBe(false);
        expect(onClose).toHaveBeenCalledOnce();
    });

    it("sets isOpen false and calls underlying close() when close() is called", () => {
        const { result } = renderHook(() => useOmnidapterConnect());
        act(() => {
            result.current.open({ token: "lt_test" });
        });
        act(() => {
            result.current.close();
        });
        expect(result.current.isOpen).toBe(false);
        expect(mockClose).toHaveBeenCalledOnce();
    });

    it("calls close() on unmount", () => {
        const { unmount } = renderHook(() => useOmnidapterConnect());
        unmount();
        expect(mockClose).toHaveBeenCalledOnce();
    });

    it("passes baseUrl option to OmnidapterConnect constructor", () => {
        renderHook(() => useOmnidapterConnect({ baseUrl: "https://custom.example.com" }));
        expect(vi.mocked(OmnidapterConnect)).toHaveBeenCalledWith({
            baseUrl: "https://custom.example.com",
        });
    });
});
