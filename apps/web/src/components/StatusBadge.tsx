import { AlertTriangle, Check, Clock3 } from "lucide-react";
import type { DecisionStatus } from "../types";

export function StatusBadge({ status }: { status: DecisionStatus }) {
  const Icon = status === "flagged" ? AlertTriangle : status === "upheld" ? Check : Clock3;
  return (
    <span className={`status status--${status}`}>
      <Icon size={13} aria-hidden="true" />
      {status}
    </span>
  );
}
