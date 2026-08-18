import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CircleGauge,
  FileCheck2,
  Menu,
  Network,
  Plus,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { api } from "./api";
import { AgentsView } from "./views/AgentsView";
import { DecisionsView } from "./views/DecisionsView";
import { PoliciesView } from "./views/PoliciesView";
import { TracesView } from "./views/TracesView";
import type { Decision, DecisionInput } from "./types";

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

function App() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
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

  async function replay(id: string) {
    setWorking(true);
    setError(undefined);
    try {
      const decision = await api.replayDecision(id);
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
          <PoliciesView />
        ) : activeNav === "Agents" ? (
          <AgentsView />
        ) : activeNav === "Traces" ? (
          <TracesView decisions={decisions} />
        ) : (
          <DecisionsView
            decisions={decisions}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onReplay={replay}
            loading={loading}
            working={working}
          />
        )}
      </main>
    </div>
  );
}

export default App;
