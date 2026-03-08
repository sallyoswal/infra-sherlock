"""CLI entrypoint for deterministic major-incident triage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cli.env_utils import load_local_env
from incident_agent.loader import IncidentDataError
from incident_agent.major_incident.correlator import triage_major_incident

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    HAS_RICH = True
except Exception:
    HAS_RICH = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="infra-sherlock-major")
    sub = parser.add_subparsers(dest="command", required=True)

    triage = sub.add_parser("triage", help="Triage a major incident group")
    triage.add_argument("incident_group_name", help="Major incident group directory name")
    triage.add_argument(
        "--datasets-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "datasets" / "major_incidents",
        help="Path to major incident dataset root",
    )
    return parser


def _render_plain(report) -> None:
    group = report.incident_group
    top_hyp = report.hypotheses[0] if report.hypotheses else None

    print(f"Incident: {group.title} ({group.group_id})")
    print(f"Severity: {group.severity} | Status: {group.status}")
    print(f"Likely initiating fault: {report.likely_initiating_fault_service}")
    if top_hyp:
        print(f"Top hypothesis: {top_hyp.title} [{top_hyp.confidence}]")
    print(f"Impacted services: {report.impacted_services_count}")
    print(f"Impacted teams: {', '.join(report.impacted_teams)}")
    print(f"Customer impact: {report.customer_facing_impact}")

    print("Top next actions:")
    for action in report.recommended_next_actions[:3]:
        print(f"- {action}")

    print("Services:")
    for svc in report.service_summaries:
        print(
            f"- {svc.service} | team={svc.team} | first_anomaly={svc.first_anomaly} | "
            f"role={svc.likely_role} | confidence={svc.confidence}"
        )


def _render_rich(report) -> None:
    console = Console()
    group = report.incident_group
    top_hyp = report.hypotheses[0] if report.hypotheses else None

    summary_lines = [
        f"[bold]Severity:[/bold] {group.severity}",
        f"[bold]Status:[/bold] {group.status}",
        f"[bold]Likely Initiating Fault:[/bold] {report.likely_initiating_fault_service}",
        f"[bold]Impacted Services:[/bold] {report.impacted_services_count}",
        f"[bold]Impacted Teams:[/bold] {', '.join(report.impacted_teams)}",
        f"[bold]Customer Impact:[/bold] {report.customer_facing_impact}",
    ]
    if top_hyp:
        summary_lines.insert(
            3,
            f"[bold]Top Hypothesis:[/bold] {top_hyp.title} ({top_hyp.confidence})",
        )

    console.print(Panel("\n".join(summary_lines), title=group.title, subtitle=group.group_id, border_style="red"))

    actions_table = Table(title="Top 3 Recommended Next Actions")
    actions_table.add_column("Action")
    for action in report.recommended_next_actions[:3]:
        actions_table.add_row(action)
    console.print(actions_table)

    services_table = Table(title="Service Triage")
    services_table.add_column("Service")
    services_table.add_column("Team")
    services_table.add_column("First Anomaly")
    services_table.add_column("Likely Role")
    services_table.add_column("Confidence")

    for svc in report.service_summaries:
        services_table.add_row(
            svc.service,
            svc.team,
            svc.first_anomaly,
            svc.likely_role,
            svc.confidence,
        )
    console.print(services_table)


def main(argv: list[str] | None = None) -> int:
    load_local_env(PROJECT_ROOT)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "triage":
        try:
            report = triage_major_incident(
                group_name=args.incident_group_name,
                datasets_root=args.datasets_root,
            )
        except IncidentDataError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

        if HAS_RICH:
            _render_rich(report)
        else:
            _render_plain(report)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
