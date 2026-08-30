import { useMemo } from "react";
import { ScrollText } from "lucide-react";
import type { Decision } from "../types";
import "./PoliciesView.css";

interface Props {
  decisions: Decision[];
}

interface Clause {
  ruleId: string;
  title: string;
  citation?: string | null;
  excerpt?: string | null;
  unmet: number;
}

interface PolicyEntry {
  policyId: string;
  version?: string;
  decisions: number;
  flagged: number;
  clauses: Clause[];
}

function buildRegistry(decisions: Decision[]): PolicyEntry[] {
  const entries = new Map<string, PolicyEntry & { clauseIndex: Map<string, Clause> }>();

  for (const decision of decisions) {
    let entry = entries.get(decision.policy_id);
    if (!entry) {
      entry = { policyId: decision.policy_id, decisions: 0, flagged: 0, clauses: [], clauseIndex: new Map() };
      entries.set(decision.policy_id, entry);
    }
    entry.decisions += 1;
    if (decision.status === "flagged") entry.flagged += 1;
    if (decision.policy_version) entry.version = decision.policy_version.split("@").slice(1).join("@") || decision.policy_version;

    for (const finding of decision.findings) {
      const clause = entry.clauseIndex.get(finding.rule_id) ?? {
        ruleId: finding.rule_id,
        title: finding.title,
        citation: finding.citation,
        excerpt: finding.source_excerpt,
        unmet: 0,
      };
      clause.citation = clause.citation ?? finding.citation;
      clause.excerpt = clause.excerpt ?? finding.source_excerpt;
      if (!finding.satisfied) clause.unmet += 1;
      entry.clauseIndex.set(finding.rule_id, clause);
    }
  }

  return [...entries.values()]
    .map(({ clauseIndex, ...entry }) => ({ ...entry, clauses: [...clauseIndex.values()] }))
    .sort((a, b) => a.policyId.localeCompare(b.policyId));
}

export function PoliciesView({ decisions }: Props) {
  const policies = useMemo(() => buildRegistry(decisions), [decisions]);

  return (
    <section className="registry-view">
      <div className="registry-view__header">
        <div><p className="eyebrow">Governing rules</p><h2>Policy registry</h2></div>
        <span className="mini-state mini-state--active">{policies.length} in force</span>
      </div>

      {policies.length === 0 ? (
        <div className="registry-empty">No policy has been exercised yet. Process a decision to populate the registry.</div>
      ) : (
        <div className="registry-table">
          <div className="registry-row registry-row--header"><span>Policy</span><span>Version</span><span>Clauses</span><span>State</span></div>
          {policies.map((policy) => (
            <div className="policy-entry" key={policy.policyId}>
              <div className="registry-row">
                <strong>{policy.policyId}</strong>
                <code>{policy.version ?? "unversioned"}</code>
                <span>{policy.clauses.length} extracted {policy.clauses.length === 1 ? "constraint" : "constraints"}</span>
                <span className={`mini-state ${policy.flagged > 0 ? "mini-state--alert" : "mini-state--active"}`}>
                  {policy.flagged > 0 ? `${policy.flagged} flagged` : "Clean"}
                </span>
              </div>
              <ul className="clause-list">
                {policy.clauses.map((clause) => (
                  <li key={clause.ruleId}>
                    <div className="clause-head">
                      <ScrollText size={13} aria-hidden="true" />
                      <code>{clause.citation ?? clause.ruleId}</code>
                      <strong>{clause.title}</strong>
                      <span className={clause.unmet > 0 ? "clause-tally clause-tally--unmet" : "clause-tally"}>
                        {clause.unmet > 0 ? `unmet in ${clause.unmet} of ${policy.decisions}` : `met in all ${policy.decisions}`}
                      </span>
                    </div>
                    {clause.excerpt && <blockquote>{clause.excerpt}</blockquote>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
