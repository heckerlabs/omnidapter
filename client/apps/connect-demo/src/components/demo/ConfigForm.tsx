import React from "react";
import { Config } from "../../types";
import { Field } from "../common/Field";

interface ConfigFormProps {
  config: Config;
  setConfig: React.Dispatch<React.SetStateAction<Config>>;
  styles: Record<string, React.CSSProperties>;
}

export function ConfigForm({ config, setConfig, styles }: ConfigFormProps) {
  const updateConfig = (key: keyof Config, value: string) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <section style={styles.section}>
      <h2 style={styles.sectionTitle}>Configuration</h2>
      <Field
        styles={styles}
        label="API URL"
        value={config.apiUrl}
        onChange={(v) => updateConfig("apiUrl", v)}
        placeholder="http://localhost:8000"
      />
      <Field
        styles={styles}
        label="Connect UI URL"
        value={config.connectUiUrl}
        onChange={(v) => updateConfig("connectUiUrl", v)}
        placeholder="http://localhost:5123"
      />
      <Field
        styles={styles}
        label="API Key"
        value={config.apiKey}
        onChange={(v) => updateConfig("apiKey", v)}
        placeholder="omni_live_…"
        type="password"
        warning="API keys are server-side secrets. Only use one here for local testing — never in production client-side code."
      />
      <Field
        styles={styles}
        label="End User ID"
        value={config.endUserId}
        onChange={(v) => updateConfig("endUserId", v)}
        placeholder="user_123"
      />
      <Field
        styles={styles}
        label="Allowed Providers"
        value={config.allowedProviders}
        onChange={(v) => updateConfig("allowedProviders", v)}
        placeholder="google, microsoft  (blank = all)"
      />
    </section>
  );
}
