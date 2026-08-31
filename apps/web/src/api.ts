import type { Decision, DecisionInput } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

/** Agent Registry card. Mirrors app.agents.registry.AgentCard. */
export interface AgentCard {
  id: string;
  name: string;
  role: string;
  kind: "deterministic" | "model" | "solver" | "shield" | "ledger";
  version: string;
  runtime: string;
  health: "online" | "degraded" | "offline";
  detail: string;
  capabilities: string[];
}

export interface FleetDescription {
  app_name: string;
  runtime: string;
  mode: string;
  orchestrator: string;
  trace_exporter: string;
  agents: AgentCard[];
}

/** One sealed hop of one decision. Mirrors app.store.LedgerEntry. */
export interface LedgerEntry {
  decision_id: string;
  sequence: number;
  kind: string;
  agent: string;
  message: string;
  recorded_at: string;
  trace_id?: string | null;
  span_id?: string | null;
  payload: Record<string, unknown>;
  previous_hash: string;
  entry_hash: string;
}

export interface SpanView {
  name: string;
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  duration_ms: number;
  attributes: Record<string, unknown>;
}

export interface TracePage {
  exporter: string;
  entries: LedgerEntry[];
  spans: SpanView[];
}

export interface LedgerVerification {
  decision_id: string;
  intact: boolean;
  entries: number;
  head_hash: string;
  broken_at?: number | null;
  detail: string;
}

export interface Timeline {
  decision_id: string;
  verification: LedgerVerification;
  entries: LedgerEntry[];
  fork_points: string[];
}

export interface ForkRequest {
  fork_after?: string;
  fact_overrides?: Record<string, boolean | number>;
  original_decision?: "approved" | "denied";
  note?: string;
}

export const api = {
  listDecisions: () => request<Decision[]>("/api/v1/decisions"),
  createDecision: (input: DecisionInput) =>
    request<Decision>("/api/v1/decisions", { method: "POST", body: JSON.stringify(input) }),
  replayDecision: (id: string) =>
    request<Decision>(`/api/v1/decisions/${id}/replay`, {
      method: "POST",
      body: JSON.stringify({ original_decision: "approved" }),
    }),
  forkDecision: (id: string, fork: ForkRequest) =>
    request<Decision>(`/api/v1/decisions/${id}/fork`, {
      method: "POST",
      body: JSON.stringify(fork),
    }),
  describeFleet: () => request<FleetDescription>("/api/v1/fleet"),
  listTraces: (limit = 200) => request<TracePage>(`/api/v1/traces?limit=${limit}`),
  getTimeline: (id: string) => request<Timeline>(`/api/v1/decisions/${id}/timeline`),
};
