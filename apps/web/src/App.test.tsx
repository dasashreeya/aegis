import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import App from "./App";
import type { Decision } from "./types";

const decision: Decision = {
  id: "AD-TEST0001",
  source: "Benefits Engine",
  subject: "Case 2048",
  requested_service: "Post-acute skilled nursing care",
  original_decision: "denied",
  status: "flagged",
  policy_id: "CMS-SNF-100",
  rationale: "The governing eligibility constraints are satisfied, but the source decision was denied.",
  unsat_core: ["medical_necessity", "original_denied"],
  findings: [
    {
      rule_id: "medical_necessity",
      title: "Medical necessity",
      satisfied: true,
      explanation: "The case documents medical necessity.",
    },
  ],
  events: [
    {
      id: "event-1",
      kind: "solver.completed",
      agent: "Reconcile",
      message: "Formal solver found a contradiction in the original decision.",
      created_at: "2026-08-17T12:00:00Z",
    },
  ],
  created_at: "2026-08-17T12:00:00Z",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Aegis dashboard", () => {
  it("renders an audited decision and its formal finding", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify([decision]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    render(<App />);

    await waitFor(() => expect(screen.getAllByText("Case 2048").length).toBeGreaterThan(0));
    expect(screen.getByText("Unsupported denial detected")).toBeInTheDocument();
    expect(screen.getByText("Z3 verified")).toBeInTheDocument();
  });
});
