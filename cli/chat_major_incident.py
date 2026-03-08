"""Interactive deterministic chat for major incidents."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cli.env_utils import load_local_env
from cli.intent_classifier import classify_user_input
from cli.response_formatter import ChatRenderer
from incident_agent.loader import IncidentDataError
from incident_agent.major_incident.chat import (
    MajorIncidentChatError,
    MajorIncidentChatSession,
    ask_major_incident_question,
)
from incident_agent.major_incident.correlator import triage_major_incident


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="infra-sherlock-major-chat")
    parser.add_argument("incident_group_name", help="Major incident group directory name")
    parser.add_argument(
        "--datasets-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "datasets" / "major_incidents",
        help="Path to major incident dataset root",
    )
    return parser


def _overview(report) -> str:
    g = report.incident_group
    h = report.hypotheses[0] if report.hypotheses else None
    p = report.failure_patterns[0] if report.failure_patterns else None
    return (
        f"{g.severity} {g.status}: {g.title}\n"
        f"Likely initiating service: {report.likely_initiating_fault_service}\n"
        f"Likely fault domain: {report.likely_fault_domain} ({report.likely_infrastructure_layer})\n"
        f"Top hypothesis: {h.title if h else 'n/a'}\n"
        f"Top pattern match: {p.pattern_name if p else 'n/a'} ({p.confidence if p else 'n/a'})\n"
        f"Customer impact: {report.customer_facing_impact}"
    )


def _services(report) -> str:
    lines = ["Services:"]
    for s in report.service_summaries:
        lines.append(
            f"- {s.service} ({s.team}) first={s.first_anomaly[11:16]} role={s.likely_role} confidence={s.confidence}"
        )
    return "\n".join(lines)


def _blast_radius(report) -> str:
    br = report.incident_group.blast_radius
    return (
        f"Impacted services: {', '.join(br.impacted_services)}\n"
        f"Impacted teams: {', '.join(br.impacted_teams)}\n"
        f"Impacted user flows: {', '.join(br.impacted_user_flows)}\n"
        f"Regions: {', '.join(br.impacted_regions)}"
    )


def _timeline(report) -> str:
    lines = ["Timeline:"]
    for e in report.merged_timeline[:12]:
        lines.append(f"- {e.timestamp[11:16]} [{e.service or e.source}] {e.event}")
    return "\n".join(lines)


def _hypotheses(report) -> str:
    lines = ["Hypotheses:"]
    for idx, h in enumerate(report.hypotheses, start=1):
        lines.append(f"{idx}. {h.title} ({h.confidence}, role={h.likely_role})")
    if report.failure_patterns:
        lines.append("")
        lines.append("Failure patterns:")
        for p in report.failure_patterns[:3]:
            lines.append(f"- {p.pattern_name} ({p.confidence})")
    return "\n".join(lines)


def _service(report, service_name: str) -> str:
    target = next((s for s in report.service_summaries if s.service == service_name), None)
    if not target:
        return f"Service not found in major incident: {service_name}"
    lines = [
        f"Service: {target.service}",
        f"Team: {target.team}",
        f"First anomaly: {target.first_anomaly}",
        f"Likely role: {target.likely_role} ({target.confidence})",
        "Evidence:",
    ]
    lines.extend(f"- {e}" for e in target.evidence)
    return "\n".join(lines)


def _next_steps(report) -> str:
    lines = ["Next steps:"]
    lines.append(f"- Fastest validation: {report.fastest_validation_step}")
    lines.extend(f"- {s}" for s in report.recommended_next_actions)
    return "\n".join(lines)


def _help() -> str:
    return (
        "Commands: /overview, /services, /blast-radius, /timeline, /hypotheses, "
        "/service <service_name>, /next-steps, /help, /exit"
    )


def _handle_intent(intent: str, raw: str, report) -> tuple[str | None, str]:
    """Resolve shared intent classifier output into a major-incident response."""
    if intent == "help":
        return _help(), "help"
    if intent == "summary":
        return _overview(report), "overview"
    if intent == "timeline":
        return _timeline(report), "timeline"
    if intent == "evidence":
        return _hypotheses(report), "hypotheses"
    if intent == "remediation":
        return _next_steps(report), "next-steps"
    if intent == "root-cause":
        return _hypotheses(report), "hypotheses"
    if intent == "question":
        return None, raw
    return None, raw


def main(argv: list[str] | None = None) -> int:
    load_local_env(PROJECT_ROOT)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        report = triage_major_incident(args.incident_group_name, datasets_root=args.datasets_root)
    except IncidentDataError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    renderer = ChatRenderer()
    chat_session = MajorIncidentChatSession(report=report)
    renderer.print_llm_answer("Infra Sherlock Major Incident Chat")
    renderer.print_llm_answer(_overview(report))
    renderer.print_llm_answer(_help())

    last_mode = "overview"

    while True:
        try:
            raw = input("> ").strip()
        except EOFError:
            print()
            break

        if not raw:
            continue
        if raw.lower() in {"/exit", "exit", "quit", "/quit"}:
            break

        cmd = raw.lower()
        if cmd in {"/help", "help"}:
            renderer.print_llm_answer(_help())
            last_mode = "help"
            continue
        if cmd in {"/overview", "overview", "what happened", "status"}:
            renderer.print_llm_answer(_overview(report))
            last_mode = "overview"
            continue
        if cmd in {"/services", "services"}:
            renderer.print_llm_answer(_services(report))
            last_mode = "services"
            continue
        if cmd in {"/blast-radius", "blast radius"}:
            renderer.print_llm_answer(_blast_radius(report))
            last_mode = "blast-radius"
            continue
        if cmd in {"/timeline", "timeline", "when"}:
            renderer.print_llm_answer(_timeline(report))
            last_mode = "timeline"
            continue
        if cmd in {"/hypotheses", "hypothesis", "hypotheses"}:
            renderer.print_llm_answer(_hypotheses(report))
            last_mode = "hypotheses"
            continue
        if cmd in {"/next-steps", "next steps", "what should we do"}:
            renderer.print_llm_answer(_next_steps(report))
            last_mode = "next-steps"
            continue
        if cmd.startswith("/service "):
            service_name = raw.split(" ", 1)[1].strip()
            renderer.print_llm_answer(_service(report, service_name))
            last_mode = "service"
            continue
        if raw.startswith("/") and cmd not in {
            "/summary",
            "/root",
            "/timeline",
            "/evidence",
            "/remediation",
        }:
            renderer.print_llm_answer("Unknown command. Use /help.")
            continue

        # Keep free-form chat as primary for longer natural-language prompts.
        if not raw.startswith("/") and len(cmd.split()) > 3:
            intent_result = classify_user_input(raw, last_intent=None)
            try:
                answer = ask_major_incident_question(
                    session=chat_session,
                    question=raw,
                    concise=not intent_result.detailed,
                )
            except MajorIncidentChatError as exc:
                renderer.print_llm_answer(f"Error: {exc}")
                continue
            renderer.print_llm_answer(answer)
            continue

        intent_result = classify_user_input(raw, last_intent=last_mode if last_mode in {
            "summary",
            "root-cause",
            "timeline",
            "remediation",
            "evidence",
        } else None)
        rendered, mode = _handle_intent(intent_result.intent, raw, report)
        if rendered is not None:
            renderer.print_llm_answer(rendered)
            if mode in {"overview", "timeline", "hypotheses", "next-steps", "help"}:
                last_mode = mode
            continue

        if cmd in {"and services?", "services?"}:
            renderer.print_llm_answer(_services(report))
            last_mode = "services"
            continue

        # Free chat fallback for non-command input.
        try:
            answer = ask_major_incident_question(
                session=chat_session,
                question=raw,
                concise=not intent_result.detailed,
            )
        except MajorIncidentChatError as exc:
            renderer.print_llm_answer(f"Error: {exc}")
            continue
        renderer.print_llm_answer(answer)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
