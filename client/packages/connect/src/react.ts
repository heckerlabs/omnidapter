import { useCallback, useEffect, useRef, useState } from "react";
import { OmnidapterConnect } from "./index";
import type { OmnidapterConnectOptions, OpenOptions } from "./index";

/**
 * React hook for Omnidapter Connect.
 * Note: `options` (including `baseUrl`) are read only on mount and not updated if the prop changes.
 */
export function useOmnidapterConnect(options?: OmnidapterConnectOptions): {
    open: (options: OpenOptions) => void;
    close: () => void;
    isOpen: boolean;
} {
    const connectRef = useRef<OmnidapterConnect | null>(null);
    const [isOpen, setIsOpen] = useState(false);

    useEffect(() => {
        connectRef.current = new OmnidapterConnect(options);
        return () => {
            connectRef.current?.close();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const open = useCallback((openOptions: OpenOptions) => {
        setIsOpen(true);
        connectRef.current?.open({
            ...openOptions,
            onSuccess: (result) => {
                setIsOpen(false);
                openOptions.onSuccess?.(result);
            },
            onError: (error) => {
                setIsOpen(false);
                openOptions.onError?.(error);
            },
            onClose: () => {
                setIsOpen(false);
                openOptions.onClose?.();
            },
        });
    }, []);

    const close = useCallback(() => {
        connectRef.current?.close();
        setIsOpen(false);
    }, []);

    return { open, close, isOpen };
}
