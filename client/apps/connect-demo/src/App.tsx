import { useState, useEffect, useRef } from "react";
import { OmnidapterConnect } from "@heckerlabs/omnidapter-connect";
import { DEFAULT_CONFIG, STORAGE_KEY } from "./constants";
import { Config, Mode } from "./types";
import { inIframe } from "./utils/helpers";
import { fetchLinkToken } from "./utils/api";
import { useLogger } from "./hooks/useLogger";
import { useTheme } from "./hooks/useTheme";
import { getStyles } from "./styles/appStyles";
import { Header } from "./components/layout/Header";
import { ModeTabs } from "./components/demo/ModeTabs";
import { ConfigForm } from "./components/demo/ConfigForm";
import { EventLog } from "./components/demo/EventLog";
import { EmbedModal } from "./components/demo/EmbedModal";
import { IframeCallback } from "./components/demo/IframeCallback";

export function App() {
    const { theme, toggleTheme } = useTheme();
    const { log, addLog, clearLog, logEndRef } = useLogger();

    const [config, setConfig] = useState<Config>(() => {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            return saved ? { ...DEFAULT_CONFIG, ...JSON.parse(saved) } : DEFAULT_CONFIG;
        } catch {
            return DEFAULT_CONFIG;
        }
    });

    const [mode, setMode] = useState<Mode>(() => {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            const parsed = saved ? JSON.parse(saved) : null;
            return (["popup", "redirect", "embed"] as Mode[]).includes(parsed?.mode)
                ? parsed.mode
                : "popup";
        } catch {
            return "popup";
        }
    });

    const [loading, setLoading] = useState(false);
    const [embedSrc, setEmbedSrc] = useState<string | null>(null);
    const sdkRef = useRef<OmnidapterConnect | null>(null);
    const initRef = useRef(false);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...config, mode, theme }));
    }, [config, mode, theme]);

    const params = new URLSearchParams(window.location.search);
    const cbConnectionId = params.get("connection_id");
    const cbStatus = params.get("status");
    const cbError = params.get("error");
    const cbErrorDesc = params.get("error_description");
    const isEmbedCallback =
        inIframe() && (cbConnectionId !== null || cbError !== null || cbStatus === "cancelled");

    const styles = getStyles();

    useEffect(() => {
        if (!isEmbedCallback || initRef.current) return;
        initRef.current = true;

        if (cbConnectionId) {
            window.parent.postMessage(
                { type: "omnidapter:success", connectionId: cbConnectionId, provider: "" },
                "*"
            );
        } else if (cbStatus === "cancelled") {
            window.parent.postMessage({ type: "omnidapter:close" }, "*");
        } else {
            window.parent.postMessage(
                { type: "omnidapter:error", code: cbError, message: cbErrorDesc ?? "" },
                "*"
            );
        }
    }, [cbConnectionId, cbError, cbErrorDesc, cbStatus, isEmbedCallback]);

    useEffect(() => {
        if (isEmbedCallback || initRef.current) return;
        initRef.current = true;

        if (cbConnectionId) {
            addLog("success", "Connected via redirect", `connection_id: ${cbConnectionId}`);
            window.history.replaceState({}, "", window.location.pathname);
        } else if (cbStatus === "cancelled") {
            addLog("info", "Cancelled via redirect");
            window.history.replaceState({}, "", window.location.pathname);
        } else if (cbError) {
            addLog("error", `Error via redirect: ${cbError}`, cbErrorDesc ?? undefined);
            window.history.replaceState({}, "", window.location.pathname);
        }
    }, [addLog, cbConnectionId, cbError, cbErrorDesc, cbStatus, isEmbedCallback]);

    useEffect(() => {
        if (!embedSrc) return;

        const handler = (event: MessageEvent) => {
            const data = event.data as
                | {
                      type?: string;
                      connectionId?: string;
                      code?: string;
                      message?: string;
                      provider?: string;
                  }
                | undefined;
            if (!data?.type?.startsWith("omnidapter:")) return;
            if (data.type === "omnidapter:success") {
                addLog(
                    "success",
                    "Connected via embed",
                    `connection_id: ${data.connectionId}${
                        data.provider ? `, provider: ${data.provider}` : ""
                    }`
                );
                setEmbedSrc(null);
            } else if (data.type === "omnidapter:close") {
                addLog("info", "Cancelled via embed");
                setEmbedSrc(null);
            } else if (data.type === "omnidapter:error") {
                addLog("error", `Error via embed: ${data.code}`, data.message);
                setEmbedSrc(null);
            }
        };
        window.addEventListener("message", handler);
        return () => window.removeEventListener("message", handler);
    }, [addLog, embedSrc]);

    useEffect(() => {
        sdkRef.current = null;
    }, [config.connectUiUrl]);

    if (isEmbedCallback) {
        return <IframeCallback connectionId={cbConnectionId} styles={styles} />;
    }

    const handleConnect = async () => {
        if (!config.apiKey.trim()) {
            addLog("error", "API key is required");
            return;
        }

        setLoading(true);
        addLog("info", `Creating link token (mode: ${mode})…`);

        try {
            const redirectUri =
                mode !== "popup"
                    ? `${window.location.origin}${window.location.pathname}`
                    : undefined;
            const token = await fetchLinkToken(config, redirectUri);
            addLog("info", "Link token created", `${token.slice(0, 14)}…`);

            if (mode === "popup") {
                sdkRef.current ??= new OmnidapterConnect({ baseUrl: config.connectUiUrl });
                sdkRef.current.open({
                    token,
                    onSuccess: ({ connectionId, provider }) =>
                        addLog(
                            "success",
                            "Connected via popup",
                            `connection_id: ${connectionId}, provider: ${provider}`
                        ),
                    onError: ({ code, message }) =>
                        addLog("error", `Error via popup: ${code}`, message),
                    onClose: () => addLog("info", "Popup closed by user"),
                });
            } else if (mode === "redirect") {
                addLog("info", "Redirecting to Connect UI…");
                window.location.href = `${config.connectUiUrl}?token=${encodeURIComponent(token)}`;
            } else {
                setEmbedSrc(`${config.connectUiUrl}?token=${encodeURIComponent(token)}`);
                addLog("info", "Embed modal opened");
            }
        } catch (err: unknown) {
            addLog("error", err instanceof Error ? err.message : "Unknown error");
        } finally {
            setLoading(false);
        }
    };

    const handleCloseEmbed = () => {
        setEmbedSrc(null);
        addLog("info", "Embed closed by user");
    };

    const connectLabel: Record<Mode, string> = {
        popup: "Open Popup",
        redirect: "Redirect to Connect",
        embed: "Open Embedded",
    };

    return (
        <div style={styles.root}>
            <style>{`
        .demo-body { grid-template-columns: 360px 1fr; }
        @media (max-width: 720px) {
          .demo-body { grid-template-columns: 1fr; }
          .demo-log { border-top: 1px solid #e5e7eb; border-left: none; }
          .demo-log-panel { max-height: 280px; }
          .demo-title { font-size: 16px !important; }
        }
        * { scrollbar-width: thin; scrollbar-color: var(--input-border) var(--bg-secondary); }
        *::-webkit-scrollbar { width: 6px; height: 6px; }
        *::-webkit-scrollbar-track { background: var(--bg-secondary); }
        *::-webkit-scrollbar-thumb { background: var(--input-border); border-radius: 3px; }
        *::-webkit-scrollbar-thumb:hover { background: var(--text-tertiary); }
      `}</style>

            <Header theme={theme} onToggleTheme={toggleTheme} styles={styles} />

            <div style={styles.body} className="demo-body">
                <div style={styles.left}>
                    <ModeTabs mode={mode} setMode={setMode} styles={styles} />

                    <ConfigForm config={config} setConfig={setConfig} styles={styles} />

                    <button
                        style={{
                            ...styles.connectBtn,
                            ...(loading ? styles.connectBtnDisabled : {}),
                        }}
                        onClick={handleConnect}
                        disabled={loading}
                    >
                        {loading ? "Working…" : connectLabel[mode]}
                    </button>
                </div>

                <EventLog log={log} onClear={clearLog} logEndRef={logEndRef} styles={styles} />
            </div>

            {embedSrc && <EmbedModal src={embedSrc} onClose={handleCloseEmbed} styles={styles} />}
        </div>
    );
}
