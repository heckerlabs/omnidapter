import { useState, useRef, useEffect, useCallback } from "react";
import { LogEntry } from "../types";
import { now } from "../utils/helpers";

export function useLogger() {
  const [log, setLog] = useState<LogEntry[]>(() => {
    try {
      const saved = sessionStorage.getItem("omnidapter_demo_log");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const logIdRef = useRef(log.reduce((max, e) => Math.max(max, e.id), 0));
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    sessionStorage.setItem("omnidapter_demo_log", JSON.stringify(log));
  }, [log]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log]);

  const addLog = useCallback(
    (level: LogEntry["level"], message: string, detail?: string) => {
      setLog((prev) => [
        ...prev,
        { id: ++logIdRef.current, time: now(), level, message, detail },
      ]);
    },
    []
  );

  const clearLog = useCallback(() => {
    setLog([]);
    sessionStorage.removeItem("omnidapter_demo_log");
  }, []);

  return { log, addLog, clearLog, logEndRef };
}
