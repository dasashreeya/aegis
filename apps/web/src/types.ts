export type DecisionStatus = "flagged" | "upheld" | "pending";

export interface AuditEvent {
  id: string;
  kind: string;
  agent: string;
  message: string;
  created_at: string;
  trace_id?: string | null;
  span_id?: string | null;
}

export interface RuleFinding {
  rule_id: string;
  title: string;
  satisfied: boolean;
  explanation: string;
  citation?: string | null;
  source_excerpt?: string | null;
}

export interface Decision {
  id: string;
  source: string;
  subject: string;
  requested_service: string;
  original_decision: "approved" | "denied";
  status: DecisionStatus;
  policy_id: string;
  rationale: string;
  unsat_core: string[];
  relaxations: string[];
  policy_version?: string | null;
  findings: RuleFinding[];
  events: AuditEvent[];
  created_at: string;
  replay_of?: string | null;
}

export interface DecisionInput {
  source: string;
  subject: string;
  requested_service: string;
  original_decision: "approved" | "denied";
  policy_id: string;
  facts: {
    medically_necessary: boolean;
    skilled_care_required: boolean;
    benefit_days_used: number;
    requested_days: number;
  };
}

