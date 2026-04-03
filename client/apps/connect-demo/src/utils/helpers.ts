export function inIframe(): boolean {
    try {
        return window !== window.top;
    } catch {
        return true;
    }
}

export function now(): string {
    const d = new Date();
    return [d.getHours(), d.getMinutes(), d.getSeconds()]
        .map((n) => String(n).padStart(2, "0"))
        .join(":");
}
