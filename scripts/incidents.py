"""Replay the recorded incident corpus through the fleet.

    python scripts/incidents.py                    # whatever .env says
    python scripts/incidents.py --live -c 8        # real Vertex, 8 at a time
    python scripts/incidents.py --report docs/incident-report.md

Every case in ``incidents/`` carries the outcome it is expected to reach. This
runs them all, compares, verifies each ledger chain, and reports the throughput
against the 1.2 seconds per claim that the ProPublica investigation recorded.

The control incident is the one that matters most. A system that flags every
denial has told you nothing; the run fails if a correct denial gets flagged.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

import _bootstrap  # noqa: F401  puts services/api on the path; must precede app imports
from app.config import Settings, get_settings
from app.corpus import Incident, load_incidents
from app.dependencies import build_stores
from app.models import DecisionInput
from app.orchestrator import DecisionOrchestrator, UnsafeDecisionError
from app.solver import EligibilitySolver
from app.telemetry import telemetry

PXDX_SECONDS_PER_CLAIM = 1.2  # ProPublica, 25 March 2023

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


@dataclass
class CaseResult:
    incident_id: str
    label: str
    expected: str
    actual: str
    latency_ms: float
    chain_intact: bool
    unsat_core: list[str] = field(default_factory=list)
    rationale: str = ""
    engine: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.actual == self.expected and self.chain_intact


@dataclass
class IncidentResult:
    incident: Incident
    cases: list[CaseResult]

    @property
    def ok(self) -> bool:
        return all(case.ok for case in self.cases)

    @property
    def flagged(self) -> int:
        return sum(1 for case in self.cases if case.actual == "flagged")

    @property
    def upheld(self) -> int:
        return sum(1 for case in self.cases if case.actual == "upheld")


async def run_case(
    orchestrator: DecisionOrchestrator,
    incident: Incident,
    label: str,
    expected: str,
    decision: DecisionInput,
    gate: asyncio.Semaphore,
) -> CaseResult:
    async with gate:
        started = time.perf_counter()
        try:
            record = await orchestrator.arun(decision)
        except UnsafeDecisionError as error:
            return CaseResult(
                incident_id=incident.id,
                label=label,
                expected=expected,
                actual="blocked",
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                chain_intact=True,
                error=str(error),
            )
        except Exception as error:  # noqa: BLE001 - one bad case must not stop the corpus
            return CaseResult(
                incident_id=incident.id,
                label=label,
                expected=expected,
                actual="error",
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                chain_intact=False,
                error=f"{type(error).__name__}: {error}",
            )
        latency = round((time.perf_counter() - started) * 1000, 1)

    adjudication = next(
        (event for event in record.events if event.kind == "adjudication.completed"), None
    )
    return CaseResult(
        incident_id=incident.id,
        label=label,
        expected=expected,
        actual=record.status,
        latency_ms=latency,
        chain_intact=orchestrator.ledger.verify(record.id).intact,
        unsat_core=list(record.unsat_core),
        rationale=record.rationale,
        engine=adjudication.message if adjudication else "",
    )


async def run_incident(
    orchestrator: DecisionOrchestrator, incident: Incident, gate: asyncio.Semaphore
) -> IncidentResult:
    cases = await asyncio.gather(
        *(
            run_case(orchestrator, incident, label, expected, decision, gate)
            for label, expected, decision in incident.cases()
        )
    )
    return IncidentResult(incident=incident, cases=list(cases))


def sweep_unknown_parameter(decision: DecisionInput) -> tuple[int, int, bool]:
    """Does the finding survive every admissible value of the unknown day count?

    Lokken's record does not say how many further days were ordered. Rather than
    pick one and hope, sweep the whole range that fits inside the benefit period
    and check the contradiction holds throughout.
    """
    solver = EligibilitySolver()
    remaining = 100 - decision.facts.benefit_days_used
    upper = max(1, min(100, remaining))
    holds = True
    for days in range(1, upper + 1):
        candidate = decision.model_copy(
            update={"facts": decision.facts.model_copy(update={"requested_days": days})}
        )
        if not solver.evaluate(candidate).conflicts_with_original:
            holds = False
            break
    return 1, upper, holds


def render(results: list[IncidentResult], settings: Settings, wall_seconds: float) -> str:
    lines: list[str] = []
    cases = [case for result in results for case in result.cases]
    passed = sum(1 for case in cases if case.ok)
    latencies = sorted(case.latency_ms for case in cases)
    mean_ms = sum(latencies) / len(latencies) if latencies else 0.0

    lines.append("# Incident replay report")
    lines.append("")
    lines.append(
        f"`{settings.mode}` mode · adjudicator `{settings.model_adjudicator}` · "
        f"{len(cases)} cases across {len(results)} incidents"
    )
    lines.append("")
    lines.append("| Incident | Cases | Flagged | Upheld | Expected outcome reached |")
    lines.append("| --- | --- | --- | --- | --- |")
    for result in results:
        mark = "all" if result.ok else f"{sum(1 for c in result.cases if c.ok)} of {len(result.cases)}"
        lines.append(
            f"| {result.incident.title} | {len(result.cases)} | {result.flagged} | "
            f"{result.upheld} | {mark} |"
        )
    lines.append("")
    lines.append(
        f"**{passed} of {len(cases)} cases reached the expected outcome with an intact "
        f"ledger chain.**"
    )
    lines.append("")
    lines.append(
        f"Mean {mean_ms:.0f} ms per audited decision, median "
        f"{latencies[len(latencies) // 2]:.0f} ms, wall clock {wall_seconds:.1f} s for the "
        f"whole corpus. PxDx spent {PXDX_SECONDS_PER_CLAIM} seconds per claim without opening "
        f"the file."
    )
    lines.append("")

    for result in results:
        incident = result.incident
        lines.append(f"## {incident.title}")
        lines.append("")
        lines.append(
            f"*{incident.operator} · {incident.system} · {incident.period}*"
            + ("  ·  **reconstructed**" if incident.reconstructed else "")
        )
        lines.append("")
        lines.append(incident.summary)
        lines.append("")
        lines.append(f"**Harm.** {incident.harm}")
        lines.append("")
        lines.append(f"**What is reconstructed.** {incident.caveat}")
        lines.append("")
        lines.append("Governing rules:")
        lines.append("")
        for rule in incident.governing_rules:
            lines.append(f"- `{rule.rule_id}` — {rule.citation}. {rule.requirement}")
        lines.append("")
        lines.append("| Case | Original | Expected | Aegis | Latency |")
        lines.append("| --- | --- | --- | --- | --- |")
        for case in result.cases[:8]:
            tick = "" if case.ok else " ⚠"
            lines.append(
                f"| {case.label} | — | {case.expected} | {case.actual}{tick} | "
                f"{case.latency_ms:.0f} ms |"
            )
        if len(result.cases) > 8:
            lines.append(f"| … {len(result.cases) - 8} more | | | | |")
        lines.append("")
        first = result.cases[0]
        if first.rationale:
            lines.append(f"> {first.rationale}")
            lines.append("")
        if first.unsat_core:
            lines.append(f"Minimal unsat core: `{'`, `'.join(first.unsat_core)}`")
            lines.append("")
        lines.append("Sources:")
        lines.append("")
        for source in incident.sources:
            lines.append(f"- [{source.title}]({source.url}) — {source.publisher}, {source.date}")
        lines.append("")

    return "\n".join(lines)


def print_console(results: list[IncidentResult], settings: Settings, wall: float) -> None:
    cases = [case for result in results for case in result.cases]
    passed = sum(1 for case in cases if case.ok)
    for result in results:
        state = "OK " if result.ok else "FAIL"
        print(f"\n{BOLD}[{state}] {result.incident.title}{RESET}")
        print(
            f"  {DIM}{result.incident.operator} | {result.incident.period} | "
            f"{len(result.cases)} cases{RESET}"
        )
        for case in result.cases[:6]:
            mark = "ok" if case.ok else "XX"
            print(
                f"   [{mark}] {case.label[:56]:<56} expected {case.expected:<8} "
                f"got {case.actual:<8} {case.latency_ms:>7.0f} ms"
            )
            if case.error:
                print(f"        {case.error[:110]}")
        if len(result.cases) > 6:
            remaining = result.cases[6:]
            bad = [case for case in remaining if not case.ok]
            print(f"   {DIM}... {len(remaining)} more, {len(bad)} not matching{RESET}")
            for case in bad[:5]:
                print(
                    f"   [XX] {case.label[:56]:<56} expected {case.expected:<8} "
                    f"got {case.actual}"
                )

    latencies = [case.latency_ms for case in cases]
    mean_ms = sum(latencies) / len(latencies) if latencies else 0.0
    print(f"\n{BOLD}Summary{RESET}")
    print(f"  mode                 : {settings.mode} ({settings.model_adjudicator})")
    print(f"  cases                : {len(cases)} across {len(results)} incidents")
    print(f"  expected outcome     : {passed}/{len(cases)}")
    print(f"  chains intact        : {sum(1 for c in cases if c.chain_intact)}/{len(cases)}")
    print(f"  mean per decision    : {mean_ms:.0f} ms")
    print(f"  wall clock           : {wall:.1f} s")
    print(f"  PxDx, for comparison : {PXDX_SECONDS_PER_CLAIM * 1000:.0f} ms per claim, unread")


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.live:
        settings = Settings(**{**settings.model_dump(), "mode": "live"})
    elif args.mock:
        # The deterministic core on its own: shield, solver, ledger, no model.
        settings = Settings(**{**settings.model_dump(), "mode": "mock"})
    telemetry.configure(settings)
    store, ledger = build_stores(settings)
    orchestrator = DecisionOrchestrator(store, ledger, settings, EligibilitySolver())

    incidents = load_incidents()
    if args.incident:
        incidents = [item for item in incidents if item.id == args.incident]
        if not incidents:
            print(f"No incident with id {args.incident!r}")
            return 2

    print(f"{BOLD}Replaying {sum(i.case_count for i in incidents)} recorded decisions{RESET}")
    print(
        f"{DIM}runtime {orchestrator.fleet.runtime} | mode {settings.mode} | "
        f"concurrency {args.concurrency}{RESET}"
    )

    gate = asyncio.Semaphore(args.concurrency)
    started = time.perf_counter()
    results = [await run_incident(orchestrator, incident, gate) for incident in incidents]
    wall = time.perf_counter() - started

    print_console(results, settings, wall)

    # The one parameter the public record does not give us.
    lokken = next((i for i in incidents if i.id == "lokken-nh-predict"), None)
    if lokken is not None:
        _, upper, holds = sweep_unknown_parameter(lokken.cases()[0][2])
        verdict = "holds for every value" if holds else "DOES NOT hold everywhere"
        print(
            f"\n{BOLD}Sensitivity{RESET}\n  Lokken's requested_days is not in the public record. "
            f"Sweeping 1..{upper} days, the contradiction {verdict}."
        )

    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(results, settings, wall), encoding="utf-8")
        print(f"\n  report written to {path}")

    failures = [case for result in results for case in result.cases if not case.ok]
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the recorded incident corpus")
    parser.add_argument("--live", action="store_true", help="force real Vertex AI calls")
    parser.add_argument(
        "--mock", action="store_true", help="force the deterministic core, no model, no network"
    )
    parser.add_argument("--incident", help="run a single incident by id")
    parser.add_argument(
        "-c", "--concurrency", type=int, default=8, help="decisions audited in parallel"
    )
    parser.add_argument("--report", help="write a markdown report to this path")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
