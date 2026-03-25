/**
 * Connect UI API client.
 *
 * All requests use the link token stored in memory — never persisted to
 * localStorage or sessionStorage.
 */

import type { Provider } from "./types";

const BASE = "";

async function request<T>(
  method: string,
  path: string,
  token: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const data = await res.json();

  if (!res.ok) {
    const err = data?.error ?? data?.detail ?? {};
    throw { status: res.status, code: err.code ?? "api_error", message: err.message ?? "Unknown error" };
  }

  return data as T;
}

export async function listProviders(token: string): Promise<Provider[]> {
  const data = await request<{ providers: Provider[] }>("GET", "/connect/providers", token);
  return data.providers;
}

export interface CreateConnectionResult {
  connection_id: string;
  status: string;
  authorization_url: string | null;
}

export async function createConnection(
  token: string,
  payload: {
    provider_key: string;
    redirect_uri?: string;
    credentials?: Record<string, string>;
  }
): Promise<CreateConnectionResult> {
  const data = await request<{ data: CreateConnectionResult }>(
    "POST",
    "/connect/connections",
    token,
    payload
  );
  return data.data;
}
