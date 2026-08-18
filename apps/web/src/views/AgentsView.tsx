import { Network } from "lucide-react";
import "./AgentsView.css";

const agents = [
  ["Model Armor", "Input and output screening"],
  ["Rules ingestion", "Policy constraint extraction"],
  ["Reconcile", "Z3 contradiction analysis"],
  ["Re-adjudication", "Independent decision review"],
];

export function AgentsView() {
  return (
    <section className="registry-view">
      <div className="registry-view__header"><div><p className="eyebrow">Agent Registry</p><h2>Governed fleet</h2></div><span className="mini-state mini-state--active">4 online</span></div>
      <div className="agent-grid">
        {agents.map(([name, role]) => (
          <article className="agent-item" key={name}><span className="agent-item__icon"><Network size={17} /></span><div><strong>{name}</strong><p>{role}</p></div><span className="agent-item__online" title="Online" /></article>
        ))}
      </div>
    </section>
  );
}
