import { useState, useEffect, useRef, useCallback } from "react";
import { OmnidapterConnect } from "@omnidapter/connect-sdk";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Config {
  apiUrl: string;
  connectUiUrl: string;
  apiKey: string;
  endUserId: string;
  allowedProviders: string;
}

type Mode = "popup" | "redirect" | "embed";
type Theme = "system" | "light" | "dark";

interface LogEntry {
  id: number;
  time: string;
  level: "info" | "success" | "error";
  message: string;
  detail?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STORAGE_KEY = "omnidapter_demo_config";

const DEFAULT_CONFIG: Config = {
  apiUrl: "http://localhost:8000",
  connectUiUrl: "http://localhost:5123",
  apiKey: "",
  endUserId: "demo_user",
  allowedProviders: "",
};

function inIframe(): boolean {
  try {
    return window !== window.top;
  } catch {
    return true;
  }
}

function now(): string {
  const d = new Date();
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}

async function fetchLinkToken(
  config: Config,
  redirectUri: string | undefined
): Promise<string> {
  const body: Record<string, unknown> = {
    end_user_id: config.endUserId || "demo_user",
  };
  if (config.allowedProviders.trim()) {
    body.allowed_providers = config.allowedProviders
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }
  if (redirectUri) {
    body.redirect_uri = redirectUri;
  }

  const res = await fetch(`${config.apiUrl}/v1/link-tokens`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${config.apiKey}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg =
      (data as { detail?: { message?: string }; error?: { message?: string } })?.detail
        ?.message ??
      (data as { error?: { message?: string } })?.error?.message ??
      `HTTP ${res.status}`;
    throw new Error(msg);
  }

  const data = (await res.json()) as { data: { token: string } };
  return data.data.token;
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export function App() {
  // -------------------------------------------------------------------------
  // Theme
  // -------------------------------------------------------------------------
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      const parsed = saved ? JSON.parse(saved) : null;
      return (["system", "light", "dark"] as Theme[]).includes(parsed?.theme)
        ? parsed.theme
        : "system";
    } catch {
      return "system";
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
  }, [theme]);

  // -------------------------------------------------------------------------
  // Iframe / redirect callback detection — runs synchronously before render
  // -------------------------------------------------------------------------
  const params = new URLSearchParams(window.location.search);
  const cbConnectionId = params.get("connection_id");
  const cbStatus = params.get("status");
  const cbError = params.get("error");
  const cbErrorDesc = params.get("error_description");
  const isEmbedCallback = inIframe() && (cbConnectionId !== null || cbError !== null || cbStatus === "cancelled");

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------

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
  const [log, setLog] = useState<LogEntry[]>(() => {
    try {
      const saved = sessionStorage.getItem("omnidapter_demo_log");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [embedSrc, setEmbedSrc] = useState<string | null>(null);
  const logIdRef = useRef(log.reduce((max, e) => Math.max(max, e.id), 0));
  const sdkRef = useRef<OmnidapterConnect | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const initRef = useRef(false);

  // Persist config, mode, and theme
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...config, mode, theme }));
  }, [config, mode, theme]);

  // Persist log to sessionStorage so redirect navigations don't wipe it
  useEffect(() => {
    sessionStorage.setItem("omnidapter_demo_log", JSON.stringify(log));
  }, [log]);

  // Scroll log to bottom
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log]);

  // -------------------------------------------------------------------------
  // Logging
  // -------------------------------------------------------------------------

  const addLog = useCallback(
    (level: LogEntry["level"], message: string, detail?: string) => {
      setLog((prev) => [
        ...prev,
        { id: ++logIdRef.current, time: now(), level, message, detail },
      ]);
    },
    []
  );

  // -------------------------------------------------------------------------
  // Initialization: handle embed callback or redirect callback (mount only)
  // -------------------------------------------------------------------------

  const s = getStyles();

  if (isEmbedCallback) {
    // Handle embed callback in effect (only runs once)
    useEffect(() => {
      if (initRef.current) return;
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
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Show minimal UI for embed callback
    return (
      <div style={s.iframeCallback}>
        <span style={{ color: cbConnectionId ? "#16a34a" : "#dc2626", fontSize: 32 }}>
          {cbConnectionId ? "✓" : "✕"}
        </span>
        <p style={{ marginTop: 8, color: "#555", fontSize: 14 }}>
          {cbConnectionId ? "Connected! Returning…" : "Error. Returning…"}
        </p>
      </div>
    );
  }

  // Handle redirect callback (mount only)
  useEffect(() => {
    if (initRef.current) return;
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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Listen for postMessage from embed iframe (only when embed is active)
  useEffect(() => {
    if (!embedSrc) return;

    const handler = (event: MessageEvent) => {
      const data = event.data as { type?: string; connectionId?: string; code?: string; message?: string; provider?: string } | undefined;
      if (!data?.type?.startsWith("omnidapter:")) return;
      if (data.type === "omnidapter:success") {
        addLog(
          "success",
          "Connected via embed",
          `connection_id: ${data.connectionId}${data.provider ? `, provider: ${data.provider}` : ""}`
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

  // -------------------------------------------------------------------------
  // Connect
  // -------------------------------------------------------------------------

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
        // embed
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

  // Reset SDK instance when Connect UI URL changes
  useEffect(() => {
    sdkRef.current = null;
  }, [config.connectUiUrl]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  const modeDesc: Record<Mode, string> = {
    popup: "Opens Connect UI in a centered popup window. Communicates result via postMessage.",
    redirect: "Navigates the full page to Connect UI, then redirects back with connection_id.",
    embed: "Renders Connect UI inside an iframe modal. Result returned via postMessage.",
  };

  const connectLabel: Record<Mode, string> = {
    popup: "Open Popup",
    redirect: "Redirect to Connect",
    embed: "Open Embedded",
  };

  return (
    <div style={s.root}>
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
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <header style={s.header}>
        <div>
          <h1 style={s.title} className="demo-title">Omnidapter Connect Demo</h1>
          <p style={s.subtitle}>Test all Connect UI integration modes</p>
        </div>
        <button
          style={s.themeBtn}
          onClick={() => setTheme(t => t === "light" ? "dark" : t === "dark" ? "system" : "light")}
          title={theme === "light" ? "Light" : theme === "dark" ? "Dark" : "System"}
        >
          {theme === "light" ? "☀" : theme === "dark" ? "☾" : "◑"}
        </button>
      </header>

      {/* ------------------------------------------------------------------ */}
      {/* Body                                                                */}
      {/* ------------------------------------------------------------------ */}
      <div style={s.body} className="demo-body">
        {/* Left panel */}
        <div style={s.left}>
          {/* Mode selector */}
          <section style={s.section}>
            <h2 style={s.sectionTitle}>Mode</h2>
            <div style={s.tabs}>
              {(["popup", "redirect", "embed"] as Mode[]).map((m) => (
                <button
                  key={m}
                  style={{ ...s.tab, ...(mode === m ? s.tabActive : {}) }}
                  onClick={() => setMode(m)}
                >
                  {m === "popup" ? "🪟 Popup" : m === "redirect" ? "↗ Redirect" : "🖼 Embed"}
                </button>
              ))}
            </div>
            <p style={s.modeDesc}>{modeDesc[mode]}</p>
          </section>

          {/* Config */}
          <section style={s.section}>
            <h2 style={s.sectionTitle}>Configuration</h2>
            <Field s={s} label="API URL" value={config.apiUrl} onChange={(v) => setConfig((c) => ({ ...c, apiUrl: v }))} placeholder="http://localhost:8000" />
            <Field s={s} label="Connect UI URL" value={config.connectUiUrl} onChange={(v) => setConfig((c) => ({ ...c, connectUiUrl: v }))} placeholder="http://localhost:5123" />
            <Field s={s} label="API Key" value={config.apiKey} onChange={(v) => setConfig((c) => ({ ...c, apiKey: v }))} placeholder="omni_live_…" type="password" warning="API keys are server-side secrets. Only use one here for local testing — never in production client-side code." />
            <Field s={s} label="End User ID" value={config.endUserId} onChange={(v) => setConfig((c) => ({ ...c, endUserId: v }))} placeholder="user_123" />
            <Field s={s} label="Allowed Providers" value={config.allowedProviders} onChange={(v) => setConfig((c) => ({ ...c, allowedProviders: v }))} placeholder="google, microsoft  (blank = all)" />
          </section>

          <button
            style={{ ...s.connectBtn, ...(loading ? s.connectBtnDisabled : {}) }}
            onClick={handleConnect}
            disabled={loading}
          >
            {loading ? "Working…" : connectLabel[mode]}
          </button>
        </div>

        {/* Right panel — log */}
        <div style={s.right} className="demo-log">
          <div style={s.logHeader}>
            <h2 style={{ ...s.sectionTitle, marginBottom: 0 }}>Event Log</h2>
            <button style={s.clearBtn} onClick={() => { setLog([]); sessionStorage.removeItem("omnidapter_demo_log"); }}>
              Clear
            </button>
          </div>
          <div style={s.logPanel} className="demo-log-panel">
            {log.length === 0 && (
              <p style={s.logEmpty}>Events will appear here once you connect.</p>
            )}
            {log.map((entry) => (
              <div
                key={entry.id}
                style={{
                  ...s.logEntry,
                  borderLeftColor:
                    entry.level === "success"
                      ? "#16a34a"
                      : entry.level === "error"
                        ? "#dc2626"
                        : "#9ca3af",
                }}
              >
                <span style={s.logTime}>{entry.time}</span>
                <div style={s.logContent}>
                  <span
                    style={{
                      color:
                        entry.level === "success"
                          ? "#15803d"
                          : entry.level === "error"
                            ? "#dc2626"
                            : "#374151",
                      fontWeight: entry.level !== "info" ? 500 : 400,
                    }}
                  >
                    {entry.message}
                  </span>
                  {entry.detail && (
                    <span style={s.logDetail}>{entry.detail}</span>
                  )}
                </div>
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Embed modal                                                         */}
      {/* ------------------------------------------------------------------ */}
      {embedSrc && (
        <div style={s.overlay} onClick={handleCloseEmbed}>
          <div style={s.modal} onClick={(e) => e.stopPropagation()}>
            <div style={s.modalHeader}>
              <span style={s.modalTitle}>Connect</span>
              <button style={s.modalClose} onClick={handleCloseEmbed}>
                ✕
              </button>
            </div>
            <iframe
              src={embedSrc}
              style={s.iframe}
              title="Omnidapter Connect"
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Field component
// ---------------------------------------------------------------------------

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  warning,
  s,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  warning?: string;
  s: Record<string, React.CSSProperties>;
}) {
  const [tipVisible, setTipVisible] = useState(false);
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={s.fieldLabel}>{label}</label>
      <div style={{ position: "relative" }}>
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          style={{ ...s.input, ...(warning ? { paddingRight: 28 } : {}) }}
          spellCheck={false}
          autoComplete="off"
        />
        {warning && (
          <span
            style={s.warnIcon}
            onMouseEnter={() => setTipVisible(true)}
            onMouseLeave={() => setTipVisible(false)}
          >
            ⚠
            {tipVisible && <span style={s.warnTooltip}>{warning}</span>}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

function getStyles(): Record<string, React.CSSProperties> {
  return {
  root: {
    height: "100vh",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },

  header: {
    background: "var(--header-bg)",
    color: "#fff",
    padding: "20px 24px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  title: {
    fontSize: 20,
    fontWeight: 600,
    letterSpacing: -0.3,
  },
  subtitle: {
    fontSize: 13,
    color: "var(--text-tertiary)",
    marginTop: 2,
  },

  themeBtn: {
    background: "var(--theme-btn-bg)",
    border: "none",
    color: "var(--theme-btn-color)",
    cursor: "pointer",
    fontSize: 18,
    lineHeight: 1,
    padding: 4,
    width: 32,
    height: 32,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 6,
  },

  body: {
    flex: 1,
    display: "grid",
    gap: 0,
    minHeight: 0,
  },

  left: {
    padding: 24,
    borderRight: "1px solid var(--border)",
    background: "var(--bg-main)",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    minWidth: 0,
    overflowY: "auto",
  },

  right: {
    display: "flex",
    flexDirection: "column",
    background: "var(--bg-secondary)",
    minHeight: 0,
    overflow: "hidden",
  },

  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: 0.8,
    color: "var(--text-secondary)",
    marginBottom: 10,
  },

  tabs: {
    display: "flex",
    gap: 6,
    marginBottom: 10,
  },
  tab: {
    flex: 1,
    padding: "7px 0",
    fontSize: 13,
    fontWeight: 500,
    border: "1px solid var(--border)",
    borderRadius: 6,
    background: "var(--bg-main)",
    cursor: "pointer",
    color: "var(--text-secondary)",
    transition: "all 0.1s",
  },
  tabActive: {
    background: "var(--btn-active-bg)",
    color: "var(--btn-active-text)",
    border: "1px solid var(--btn-active-bg)",
  },
  modeDesc: {
    fontSize: 12,
    color: "var(--text-secondary)",
    lineHeight: 1.5,
  },
  warnIcon: {
    position: "absolute",
    right: 8,
    top: "50%",
    transform: "translateY(-50%)",
    fontSize: 13,
    color: "var(--warn-text)",
    cursor: "default",
    lineHeight: 1,
  },
  warnTooltip: {
    position: "absolute",
    right: 0,
    bottom: "calc(100% + 6px)",
    background: "var(--warn-bg)",
    border: "1px solid var(--warn-border)",
    color: "var(--warn-text)",
    borderRadius: 6,
    padding: "6px 10px",
    fontSize: 11,
    lineHeight: 1.5,
    width: 240,
    zIndex: 10,
    boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
  },

  fieldLabel: {
    display: "block",
    fontSize: 12,
    fontWeight: 500,
    color: "var(--label)",
    marginBottom: 5,
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    padding: "8px 10px",
    fontSize: 13,
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    outline: "none",
    background: "var(--bg-main)",
    color: "var(--text)",
    fontFamily: "inherit",
  },

  connectBtn: {
    marginTop: "auto",
    padding: "10px 0",
    fontSize: 14,
    fontWeight: 600,
    background: "var(--btn-active-bg)",
    color: "var(--btn-active-text)",
    border: "none",
    borderRadius: 8,
    cursor: "pointer",
    width: "100%",
  },
  connectBtnDisabled: {
    opacity: 0.5,
    cursor: "not-allowed",
  },

  logHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 24px",
    borderBottom: "1px solid var(--border)",
    background: "var(--bg-main)",
  },
  clearBtn: {
    fontSize: 12,
    color: "var(--text-secondary)",
    background: "none",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "3px 8px",
    cursor: "pointer",
  },
  logPanel: {
    flex: 1,
    overflowY: "auto",
    padding: "12px 24px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  logEmpty: {
    fontSize: 13,
    color: "var(--text-tertiary)",
    marginTop: 8,
  },
  logEntry: {
    display: "flex",
    gap: 10,
    alignItems: "flex-start",
    borderLeft: "3px solid var(--text-tertiary)",
    paddingLeft: 10,
    paddingTop: 3,
    paddingBottom: 3,
  },
  logTime: {
    fontSize: 11,
    color: "var(--text-tertiary)",
    fontVariantNumeric: "tabular-nums",
    flexShrink: 0,
    paddingTop: 1,
    fontFamily: "monospace",
  },
  logContent: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    fontSize: 13,
  },
  logDetail: {
    fontSize: 11,
    color: "var(--text-secondary)",
    fontFamily: "monospace",
  },

  // Embed modal
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.5)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 100,
  },
  modal: {
    background: "var(--bg-main)",
    borderRadius: 12,
    overflow: "hidden",
    boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
    display: "flex",
    flexDirection: "column",
    width: 480,
  },
  modalHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 16px",
    borderBottom: "1px solid var(--border)",
  },
  modalTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: "var(--text)",
  },
  modalClose: {
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: 16,
    color: "var(--text-secondary)",
    lineHeight: 1,
    padding: 4,
  },
  iframe: {
    width: "100%",
    height: 600,
    border: "none",
    display: "block",
  },

  // Iframe callback minimal UI
  iframeCallback: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    height: "100vh",
    fontFamily: "system-ui",
  },
  };
}
