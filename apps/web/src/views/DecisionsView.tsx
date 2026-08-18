import { useMemo, useState } from "react";
import { AlertTriangle, Check, ChevronRight, Filter, GitFork, RefreshCw, Search, ShieldCheck, X } from "lucide-react";
import { StatusBadge } from "../components/StatusBadge";
import { formatTime } from "../lib/format";
import type { Decision } from "../types";
import "./DecisionsView.css";

interface Props {
  decisions: Decision[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onReplay: (id: string) => void;
  loading: boolean;
  working: boolean;
}

export function DecisionsView({ decisions, selectedId, onSelect, onReplay, loading, working }: Props) {
  const [query, setQuery] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);

  const visibleDecisions = useMemo(() => {
    const term = query.trim().toLowerCase();
    const filtered = flaggedOnly ? decisions.filter((item) => item.status === "flagged") : decisions;
    return term
      ? filtered.filter((item) =>
          [item.id, item.source, item.subject, item.requested_service].some((value) =>
            value.toLowerCase().includes(term),
          ),
        )
      : filtered;
  }, [decisions, flaggedOnly, query]);

  const selected = decisions.find((item) => item.id === selectedId) ?? visibleDecisions[0];
  const flaggedCount = decisions.filter((item) => item.status === "flagged").length;
  const protectedCount = decisions.filter((item) => item.status !== "pending").length;

  return (
    <>
      <section className="metrics" aria-label="Decision metrics">
        <div><span>Decisions audited</span><strong>{decisions.length.toLocaleString()}</strong><small>Current workspace</small></div>
        <div><span>Flagged conflicts</span><strong>{flaggedCount}</strong><small>Require human review</small></div>
        <div><span>Protected decisions</span><strong>{protectedCount}</strong><small>Model Armor screened</small></div>
        <div><span>Fleet health</span><strong>100%</strong><small>All agents responding</small></div>
      </section>

      <section className="workspace">
        <div className="queue">
          <div className="section-heading">
            <div><h2>Decision queue</h2><span>{visibleDecisions.length} records</span></div>
            <div className="queue-actions">
              <label className="search-field">
                <Search size={16} />
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search decisions" />
              </label>
              <button
                className={`icon-button ${flaggedOnly ? "icon-button--active" : ""}`}
                title="Show flagged decisions only"
                aria-pressed={flaggedOnly}
                onClick={() => setFlaggedOnly((current) => !current)}
              ><Filter size={17} /></button>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead><tr><th>Decision</th><th>Source</th><th>Status</th><th>Policy</th><th>Time</th><th><span className="sr-only">Open</span></th></tr></thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} className="empty-state"><RefreshCw className="spin" size={19} />Loading decisions</td></tr>
                ) : visibleDecisions.length === 0 ? (
                  <tr><td colSpan={6} className="empty-state">No decisions found</td></tr>
                ) : visibleDecisions.map((item) => (
                  <tr className={item.id === selected?.id ? "row--selected" : ""} key={item.id} onClick={() => onSelect(item.id)}>
                    <td><strong>{item.subject}</strong><small>{item.requested_service}</small></td>
                    <td>{item.source}</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td><code>{item.policy_id}</code></td>
                    <td>{formatTime(item.created_at)}</td>
                    <td><ChevronRight size={17} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="inspector" aria-label="Decision details">
          {selected ? (
            <>
              <div className="inspector__header">
                <div><p className="eyebrow">Audit result</p><h2>{selected.subject}</h2></div>
                <StatusBadge status={selected.status} />
              </div>
              <div className={`verdict ${selected.status === "upheld" ? "verdict--upheld" : ""}`}>
                {selected.status === "upheld" ? <Check size={20} /> : <AlertTriangle size={20} />}
                <div><strong>{selected.status === "flagged" ? "Unsupported denial detected" : "Decision is supported"}</strong><p>{selected.rationale}</p></div>
              </div>

              <div className="detail-section">
                <div className="detail-title"><h3>Rule findings</h3><span>{selected.findings.filter((item) => item.satisfied).length}/{selected.findings.length} satisfied</span></div>
                <div className="findings">
                  {selected.findings.map((finding) => (
                    <div className="finding" key={finding.rule_id}>
                      <span className={finding.satisfied ? "finding__pass" : "finding__fail"}>{finding.satisfied ? <Check size={14} /> : <X size={14} />}</span>
                      <div><strong>{finding.title}</strong><p>{finding.explanation}</p></div>
                    </div>
                  ))}
                </div>
              </div>

              {selected.unsat_core.length > 0 && (
                <div className="detail-section">
                  <div className="detail-title"><h3>Minimal conflict set</h3><span>Z3 verified</span></div>
                  <div className="constraint-list">
                    {selected.unsat_core.map((rule) => <code key={rule}>{rule}</code>)}
                  </div>
                </div>
              )}

              <div className="detail-section">
                <div className="detail-title"><h3>Trace</h3><span>{selected.events.length} events</span></div>
                <ol className="timeline">
                  {selected.events.map((event) => (
                    <li key={event.id}><span /><div><strong>{event.agent}</strong><p>{event.message}</p><time>{formatTime(event.created_at)}</time></div></li>
                  ))}
                </ol>
              </div>

              <button className="secondary-button" onClick={() => onReplay(selected.id)} disabled={working}>
                <GitFork size={16} />Fork and replay
              </button>
            </>
          ) : <div className="empty-inspector"><ShieldCheck size={28} /><p>Select a decision to inspect its audit.</p></div>}
        </aside>
      </section>
    </>
  );
}
