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

export const api = {
  listDecisions: () => request<Decision[]>("/api/v1/decisions"),
  createDecision: (input: DecisionInput) =>
    request<Decision>("/api/v1/decisions", { method: "POST", body: JSON.stringify(input) }),
  replayDecision: (id: string) =>
    request<Decision>(`/api/v1/decisions/${id}/replay`, {
      method: "POST",
      body: JSON.stringify({ original_decision: "approved" }),
    }),
};

