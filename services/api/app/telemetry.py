"""OpenTelemetry wiring for the oversight fleet.

Every agent hop runs inside a span, and the ids of that span are stamped onto
the :class:`~app.models.AuditEvent` the hop emits. A decision record therefore
carries the trace id a regulator needs to pull the full reasoning chain out of
Cloud Trace, and the Traces view in the web app can group events by trace
without a second store.

Three exporters, chosen by :attr:`app.config.Settings.resolved_trace_exporter`:

``cloud``   batch export to Cloud Trace (production, and the demo footage).
``memory``  spans held in process, readable by tests and ``/api/v1/traces``.
``none``    no-op tracer.

The module imports cleanly when ``opentelemetry`` is absent -- CI installs only
the base dependency set -- and every public function degrades to a no-op that
still returns well-formed (null) ids.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised by the presence/absence of the extra
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    OTEL_AVAILABLE = False


@dataclass(frozen=True)
class SpanContext:
    """The identifiers an audit event needs to point back at a trace."""

    trace_id: str | None = None
    span_id: str | None = None

    @property
    def recorded(self) -> bool:
        return self.trace_id is not None


NO_SPAN = SpanContext()


@dataclass(frozen=True)
class RecordedSpan:
    """A finished span, flattened for the API and the Traces view."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    start_time: int
    end_time: int
    attributes: dict[str, Any]

    @property
    def duration_ms(self) -> float:
        return round((self.end_time - self.start_time) / 1_000_000, 3)


class Telemetry:
    """Process-wide tracer. Configured once at startup, then read everywhere."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._tracer: Any = None
        self._memory_exporter: Any = None
        self._provider: Any = None
        self._exporter_kind: str = "none"

    # -- lifecycle -----------------------------------------------------------
    def configure(self, settings: Settings) -> str:
        """Install a tracer provider. Idempotent; returns the exporter in use."""
        with self._lock:
            if self._tracer is not None:
                return self._exporter_kind
            kind = settings.resolved_trace_exporter
            if not OTEL_AVAILABLE or kind == "none":
                self._exporter_kind = "none" if OTEL_AVAILABLE else "unavailable"
                return self._exporter_kind

            resource = Resource.create(
                {
                    "service.name": settings.service_name,
                    "service.namespace": "aegis",
                    "deployment.environment": settings.environment,
                    "aegis.mode": settings.mode,
                }
            )
            provider = TracerProvider(
                resource=resource,
                sampler=TraceIdRatioBased(settings.trace_sample_ratio),
            )
            self._exporter_kind = self._install_processor(provider, kind, settings)
            _otel_trace.set_tracer_provider(provider)
            self._provider = provider
            self._tracer = _otel_trace.get_tracer("aegis.fleet")
            return self._exporter_kind

    def _install_processor(self, provider: Any, kind: str, settings: Settings) -> str:
        if kind == "cloud":
            try:
                from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

                exporter = CloudTraceSpanExporter(project_id=settings.google_cloud_project)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                return "cloud"
            except Exception as error:  # noqa: BLE001 - tracing never breaks a decision
                logger.warning("Cloud Trace exporter unavailable, using memory: %s", error)
                kind = "memory"
        if kind == "console":
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            return "console"
        self._memory_exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(self._memory_exporter))
        return "memory"

    def shutdown(self) -> None:
        with self._lock:
            if self._provider is not None:
                self._provider.shutdown()
            self._provider = None
            self._tracer = None
            self._memory_exporter = None
            self._exporter_kind = "none"

    # -- use -----------------------------------------------------------------
    @property
    def exporter(self) -> str:
        return self._exporter_kind

    @property
    def enabled(self) -> bool:
        return self._tracer is not None

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[SpanContext]:
        """Open a span and yield the ids to stamp onto the audit event."""
        if self._tracer is None:
            yield NO_SPAN
            return
        with self._tracer.start_as_current_span(name) as span:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(f"aegis.{key}", value)
            context = span.get_span_context()
            handle = SpanContext(
                trace_id=format(context.trace_id, "032x"),
                span_id=format(context.span_id, "016x"),
            )
            try:
                yield handle
            except Exception as error:
                span.record_exception(error)
                span.set_status(_otel_trace.Status(_otel_trace.StatusCode.ERROR, str(error)))
                raise

    def recorded_spans(self) -> list[RecordedSpan]:
        """Finished spans held in process. Empty unless the exporter is memory."""
        if self._memory_exporter is None:
            return []
        spans = []
        for span in self._memory_exporter.get_finished_spans():
            context = span.get_span_context()
            spans.append(
                RecordedSpan(
                    name=span.name,
                    trace_id=format(context.trace_id, "032x"),
                    span_id=format(context.span_id, "016x"),
                    parent_span_id=(
                        format(span.parent.span_id, "016x") if span.parent is not None else None
                    ),
                    start_time=span.start_time or 0,
                    end_time=span.end_time or 0,
                    attributes=dict(span.attributes or {}),
                )
            )
        return spans

    def clear(self) -> None:
        if self._memory_exporter is not None:
            self._memory_exporter.clear()


telemetry = Telemetry()


def instrument_app(app: Any) -> bool:
    """Attach FastAPI request spans so an HTTP trace parents the fleet spans."""
    if not OTEL_AVAILABLE:
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="api/health")
        return True
    except Exception as error:  # noqa: BLE001 - tracing never breaks a decision
        logger.debug("FastAPI instrumentation unavailable: %s", error)
        return False
