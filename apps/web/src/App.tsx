import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Check,
  ChevronRight,
  CircleGauge,
  Clock3,
  FileCheck2,
  Filter,
  GitFork,
  Menu,
  Network,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { api } from "./api";
import type { Decision, DecisionInput, DecisionStatus } from "./types";

const demoInput: DecisionInput = {
  source: "Benefits Engine",
  subject: "Case 2048",
  requested_service: "Post-acute skilled nursing care",
  original_decision: "denied",
  policy_id: "CMS-SNF-100",
  facts: {
    medically_necessary: true,
    skilled_care_required: true,
    benefit_days_used: 19,
    requested_days: 7,
  },
};

const navItems = [
  { label: "Overview", icon: CircleGauge },
  { label: "Decisions", icon: FileCheck2 },
  { label: "Policies", icon: SlidersHorizontal },
  { label: "Agents", icon: Network },
  { label: "Traces", icon: Activity },
];

function StatusBadge({ status }: { status: DecisionStatus }) {
  const Icon = status === "flagged" ? AlertTriangle : status === "upheld" ? Check : Clock3;
  return (
    <span className={`status status--${status}`}>
      <Icon size={13} aria-hidden="true" />
      {status}
    </span>
  );
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en", { hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function App() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [query, setQuery] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [activeNav, setActiveNav] = useState("Decisions");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string>();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    api
      .listDecisions()
      .then((data) => {
        setDecisions(data);
        setSelectedId(data[0]?.id);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

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

  async function runDemo() {
    setWorking(true);
    setError(undefined);
    try {
      const decision = await api.createDecision(demoInput);
      setDecisions((current) => [decision, ...current]);
      setSelectedId(decision.id);
      setActiveNav("Decisions");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to process decision");
    } finally {
      setWorking(false);
    }
  }

  async function replay() {
    if (!selected) return;
    setWorking(true);
    setError(undefined);
    try {
      const decision = await api.replayDecision(selected.id);
      setDecisions((current) => [decision, ...current]);
      setSelectedId(decision.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to replay decision");
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? "sidebar--open" : ""}`}>
        <div className="brand">
          <span className="brand__mark"><ShieldCheck size={20} /></span>
          <span>Aegis</span>
          <button className="icon-button sidebar__close" onClick={() => setMenuOpen(false)} title="Close navigation">
            <X size={18} />
          </button>
        </div>
        <nav aria-label="Primary navigation">
          {navItems.map(({ label, icon: Icon }) => (
            <button
              className={`nav-item ${activeNav === label ? "nav-item--active" : ""}`}
              key={label}
              onClick={() => { setActiveNav(label); setMenuOpen(false); }}
            >
              <Icon size={18} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar__footer">
          <span className="cloud-dot" />
          <div><strong>Fleet online</strong><small>4 agents connected</small></div>
        </div>
      </aside>

      <main>
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMenuOpen(true)} title="Open navigation">
            <Menu size={20} />
          </button>
          <div>
            <p className="eyebrow">Institutional oversight</p>
            <h1>{activeNav}</h1>
          </div>
          <button className="primary-button" onClick={runDemo} disabled={working}>
            {working ? <RefreshCw className="spin" size={17} /> : <Plus size={17} />}
            <span>Process decision</span>
          </button>
        </header>

        {error && <div className="error-banner" role="alert"><AlertTriangle size={17} />{error}</div>}

        {activeNav === "Policies" ? (
          <section className="registry-view">
            <div className="registry-view__header"><div><p className="eyebrow">Governing rules</p><h2>Policy registry</h2></div><span className="mini-state mini-state--active">Current</span></div>
            <div className="registry-table">
              <div className="registry-row registry-row--header"><span>Policy</span><span>Domain</span><span>Rules</span><span>State</span></div>
              <div className="registry-row"><strong>CMS-SNF-100</strong><span>Post-acute skilled nursing</span><span>3 constraints</span><span className="mini-state mini-state--active">Active</span></div>
            </div>
          </section>
        ) : activeNav === "Agents" ? (
          <section className="registry-view">
            <div className="registry-view__header"><div><p className="eyebrow">Agent Registry</p><h2>Governed fleet</h2></div><span className="mini-state mini-state--active">4 online</span></div>
            <div className="agent-grid">
              {[
                ["Model Armor", "Input and output screening"],
                ["Rules ingestion", "Policy constraint extraction"],
                ["Reconcile", "Z3 contradiction analysis"],
                ["Re-adjudication", "Independent decision review"],
              ].map(([name, role]) => (
                <article className="agent-item" key={name}><span className="agent-item__icon"><Network size={17} /></span><div><strong>{name}</strong><p>{role}</p></div><span className="agent-item__online" title="Online" /></article>
              ))}
            </div>
          </section>
        ) : activeNav === "Traces" ? (
          <section className="registry-view">
            <div className="registry-view__header"><div><p className="eyebrow">Observability</p><h2>Execution traces</h2></div><span>{decisions.reduce((count, item) => count + item.events.length, 0)} events</span></div>
            <div className="registry-table trace-table">
              <div className="registry-row registry-row--header"><span>Agent</span><span>Event</span><span>Decision</span><span>Time</span></div>
              {decisions.flatMap((item) => item.events.map((event) => (
                <div className="registry-row" key={event.id}><strong>{event.agent}</strong><span>{event.message}</span><code>{item.id}</code><span>{formatTime(event.created_at)}</span></div>
              )))}
              {decisions.length === 0 && <div className="registry-empty">No execution traces recorded</div>}
            </div>
          </section>
        ) : <>
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
                    <tr className={item.id === selected?.id ? "row--selected" : ""} key={item.id} onClick={() => setSelectedId(item.id)}>
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

                <button className="secondary-button" onClick={replay} disabled={working}>
                  <GitFork size={16} />Fork and replay
                </button>
              </>
            ) : <div className="empty-inspector"><ShieldCheck size={28} /><p>Select a decision to inspect its audit.</p></div>}
          </aside>
        </section>
        </>}
      </main>
    </div>
  );
}

export default App;
