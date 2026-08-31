import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Binary,
  BrainCircuit,
  Network,
  RefreshCw,
  ScrollText,
  ShieldCheck,
} from "lucide-react";
import { api, type AgentCard, type FleetDescription } from "../api";
import "./AgentsView.css";

const kindIcon = {
  deterministic: Network,
  model: BrainCircuit,
  solver: Binary,
  shield: ShieldCheck,
  ledger: ScrollText,
} as const;

const healthLabel: Record<AgentCard["health"], string> = {
  online: "online",
  degraded: "degraded",
  offline: "offline",
};

export function AgentsView() {
  const [fleet, setFleet] = useState<FleetDescription>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .describeFleet()
      .then(setFleet)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  const online = fleet?.agents.filter((agent) => agent.health === "online").length ?? 0;
  const degraded = fleet?.agents.filter((agent) => agent.health === "degraded").length ?? 0;

  return (
    <section className="registry-view">
      <div className="registry-view__header">
        <div>
          <p className="eyebrow">Agent Registry</p>
          <h2>Governed fleet</h2>
        </div>
        {fleet && (
          <span className={`mini-state ${degraded ? "" : "mini-state--active"}`}>
            {online} online{degraded ? `, ${degraded} degraded` : ""}
          </span>
        )}
      </div>

      {fleet && (
        <dl className="fleet-facts">
          <div>
            <dt>Orchestrator</dt>
            <dd>{fleet.orchestrator}</dd>
          </div>
          <div>
            <dt>Runtime</dt>
            <dd>{fleet.runtime}</dd>
          </div>
          <div>
            <dt>Mode</dt>
            <dd>{fleet.mode}</dd>
          </div>
          <div>
            <dt>Traces</dt>
            <dd>{fleet.trace_exporter}</dd>
          </div>
        </dl>
      )}

      {loading && (
        <div className="registry-empty">
          <RefreshCw className="spin" size={15} /> Loading the registry
        </div>
      )}
      {error && (
        <div className="registry-empty">
          <AlertTriangle size={15} /> {error}
        </div>
      )}

      <div className="agent-grid">
        {fleet?.agents.map((agent) => {
          const Icon = kindIcon[agent.kind];
          return (
            <article className={`agent-item agent-item--${agent.health}`} key={agent.id}>
              <span className="agent-item__icon">
                <Icon size={17} />
              </span>
              <div>
                <strong>{agent.name}</strong>
                <p>{agent.role}</p>
                <p className="agent-item__runtime">
                  <code>{agent.runtime}</code>
                  <span>v{agent.version}</span>
                </p>
                {agent.detail && <p className="agent-item__detail">{agent.detail}</p>}
                <ul className="agent-item__capabilities">
                  {agent.capabilities.map((capability) => (
                    <li key={capability}>{capability}</li>
                  ))}
                </ul>
              </div>
              <span
                className={`agent-item__online agent-item__online--${agent.health}`}
                title={healthLabel[agent.health]}
              />
            </article>
          );
        })}
      </div>
    </section>
  );
}
