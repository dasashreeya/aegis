import { formatTime } from "../lib/format";
import type { Decision } from "../types";
import "./TracesView.css";

export function TracesView({ decisions }: { decisions: Decision[] }) {
  return (
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
  );
}
