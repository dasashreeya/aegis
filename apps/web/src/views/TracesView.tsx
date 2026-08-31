import { useEffect, useState } from "react";
import { AlertTriangle, Link2, RefreshCw, ShieldAlert } from "lucide-react";
import { api, type LedgerEntry, type Timeline, type TracePage } from "../api";
import { formatTime } from "../lib/format";
import type { Decision } from "../types";
import "./TracesView.css";

const blockedKinds = new Set(["shield.blocked"]);

function shortHash(value: string | null | undefined) {
  return value ? value.slice(0, 12) : "—";
}

export function TracesView({ decisions }: { decisions: Decision[] }) {
  const [page, setPage] = useState<TracePage>();
  const [timelines, setTimelines] = useState<Record<string, Timeline>>({});
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);

  // Refetch whenever a decision is processed, so the ledger stays live.
  useEffect(() => {
    let cancelled = false;
    api
      .listTraces()
      .then((data) => !cancelled && setPage(data))
      .catch((reason: Error) => !cancelled && setError(reason.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [decisions.length]);

  // Timelines are cached per decision so switching the filter back is instant.
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    api
      .getTimeline(selected)
      .then((data) => !cancelled && setTimelines((current) => ({ ...current, [selected]: data })))
      .catch((reason: Error) => !cancelled && setError(reason.message));
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const timeline = selected ? timelines[selected] : undefined;
  const entries: LedgerEntry[] = timeline?.entries ?? page?.entries ?? [];
  const subjects = new Map(decisions.map((item) => [item.id, item.subject]));

  return (
    <section className="registry-view">
      <div className="registry-view__header">
        <div>
          <p className="eyebrow">Observability</p>
          <h2>Execution traces</h2>
        </div>
        <div className="trace-controls">
          <select
            aria-label="Filter by decision"
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            <option value="">All decisions</option>
            {decisions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id} · {item.subject}
              </option>
            ))}
          </select>
          <span className="mini-state mini-state--active">
            {entries.length} sealed · exporter {page?.exporter ?? "—"}
          </span>
        </div>
      </div>

      {timeline && (
        <div className={`chain-banner ${timeline.verification.intact ? "" : "chain-banner--broken"}`}>
          <Link2 size={15} />
          <div>
            <strong>
              {timeline.verification.intact
                ? `Chain intact over ${timeline.verification.entries} entries`
                : `Chain broken at entry ${timeline.verification.broken_at}`}
            </strong>
            <p>
              {timeline.verification.detail} Head <code>{shortHash(timeline.verification.head_hash)}</code>
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="registry-empty">
          <AlertTriangle size={15} /> {error}
        </div>
      )}

      <div className="registry-table trace-table">
        <div className="registry-row registry-row--header">
          <span>Agent</span>
          <span>Event</span>
          <span>Decision</span>
          <span>Ledger hash</span>
          <span>Trace</span>
          <span>Time</span>
        </div>
        {entries.map((entry) => (
          <div
            className={`registry-row ${blockedKinds.has(entry.kind) ? "registry-row--blocked" : ""}`}
            key={`${entry.decision_id}:${entry.sequence}`}
          >
            <strong>
              {blockedKinds.has(entry.kind) && <ShieldAlert size={13} aria-hidden="true" />}
              {entry.agent}
            </strong>
            <span>
              <code className="trace-kind">{entry.kind}</code>
              <small>{entry.message}</small>
            </span>
            <span>
              <code>{entry.decision_id}</code>
              <small>{subjects.get(entry.decision_id) ?? ""}</small>
            </span>
            <code title={entry.entry_hash}>{shortHash(entry.entry_hash)}</code>
            <code title={entry.trace_id ?? "not traced"}>{shortHash(entry.trace_id)}</code>
            <span>{formatTime(entry.recorded_at)}</span>
          </div>
        ))}
        {loading && entries.length === 0 && (
          <div className="registry-empty">
            <RefreshCw className="spin" size={15} /> Loading the ledger
          </div>
        )}
        {!loading && entries.length === 0 && (
          <div className="registry-empty">No execution traces recorded</div>
        )}
      </div>

      {page && page.spans.length > 0 && (
        <div className="span-table">
          <div className="registry-view__header">
            <div>
              <p className="eyebrow">OpenTelemetry</p>
              <h2>Spans</h2>
            </div>
            <span>{page.spans.length} recorded in process</span>
          </div>
          {page.spans.slice(-24).reverse().map((span) => (
            <div className="span-row" key={`${span.trace_id}:${span.span_id}`}>
              <code>{span.name}</code>
              <span className="span-bar">
                <span style={{ width: `${Math.min(100, span.duration_ms / 20)}%` }} />
              </span>
              <span>{span.duration_ms.toFixed(1)} ms</span>
              <code title={span.trace_id}>{shortHash(span.trace_id)}</code>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
