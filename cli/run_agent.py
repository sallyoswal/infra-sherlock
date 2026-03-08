"""CLI entrypoint for Infra Sherlock."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Support direct execution: `python cli/run_agent.py ...`
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from incident_agent.agent import investigate_incident
from incident_agent.loader import IncidentDataError
from incident_agent.models import IncidentReport
from incident_agent.reasoning.llm_reasoner import LLMReasonerError
from cli.response_formatter import report_to_markdown
from cli.env_utils import load_local_env

try:
    from rich.console import Console
    from rich.table import Table

    HAS_RICH = True
except Exception:
    HAS_RICH = False


def _render_report(report: IncidentReport) -> None:
    """Render report in human-friendly CLI output."""
    if not HAS_RICH:
        print(f"Incident: {report.incident_title} ({report.incident_name})")
        print(f"Service: {report.service_name}")
        print(f"Root Cause: {report.likely_root_cause}")
        print(f"Confidence: {report.confidence:.2f}")
        print("Evidence:")
        for item in report.key_evidence:
            print(f"- {item}")
        print("Timeline:")
        for event in report.timeline:
            print(f"- {event.timestamp} [{event.source}] {event.event}")
        print("Remediation:")
        for item in report.suggested_remediation:
            print(f"- {item}")
        print("Next steps:")
        for item in report.next_investigative_steps:
            print(f"- {item}")
        return

    console = Console()
    console.print(f"[bold]Incident:[/bold] {report.incident_title} ({report.incident_name})")
    console.print(f"[bold]Service:[/bold] {report.service_name}")
    console.print(f"[bold]Likely Root Cause:[/bold] {report.likely_root_cause}")
    console.print(f"[bold]Confidence:[/bold] {report.confidence:.2f}")

    evidence_table = Table(title="Key Evidence")
    evidence_table.add_column("Evidence")
    for item in report.key_evidence:
        evidence_table.add_row(item)
    console.print(evidence_table)

    timeline_table = Table(title="Incident Timeline")
    timeline_table.add_column("Timestamp")
    timeline_table.add_column("Source")
    timeline_table.add_column("Event")
    for event in report.timeline:
        timeline_table.add_row(event.timestamp, event.source, event.event)
    console.print(timeline_table)

    remediation_table = Table(title="Suggested Remediation")
    remediation_table.add_column("Action")
    for action in report.suggested_remediation:
        remediation_table.add_row(action)
    console.print(remediation_table)

    next_steps_table = Table(title="Next Investigative Steps")
    next_steps_table.add_column("Step")
    for step in report.next_investigative_steps:
        next_steps_table.add_row(step)
    console.print(next_steps_table)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(prog="infra-sherlock")
    subparsers = parser.add_subparsers(dest="command", required=True)

    investigate_parser = subparsers.add_parser("investigate", help="Investigate an incident")
    investigate_parser.add_argument("incident_name", help="Incident scenario name")
    investigate_parser.add_argument(
        "--mode",
        choices=["local", "cloud"],
        required=True,
        help="Investigation mode: local reads dataset files; cloud uses configured collectors only.",
    )
    investigate_parser.add_argument(
        "--service-name",
        type=str,
        default=None,
        help="Required in cloud mode: service identifier used by collectors.",
    )
    investigate_parser.add_argument(
        "--incident-title",
        type=str,
        default=None,
        help="Optional in cloud mode: incident title override for report metadata.",
    )
    investigate_parser.add_argument(
        "--datasets-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "datasets" / "incidents",
        help="Path to incidents dataset root (local mode only)",
    )
    investigate_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to export the report as markdown (e.g. report.md)",
    )
    investigate_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress terminal report output (useful with --output).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI main entrypoint."""
    load_local_env(PROJECT_ROOT)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "investigate":
        try:
            report = investigate_incident(
                incident_name=args.incident_name,
                datasets_root=args.datasets_root,
                investigation_mode=args.mode,
                service_name=args.service_name,
                incident_title=args.incident_title,
            )
        except IncidentDataError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        except LLMReasonerError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 3
        if not args.quiet:
            _render_report(report)
        if args.output:
            try:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(report_to_markdown(report), encoding="utf-8")
                if not args.quiet:
                    print(f"Markdown report written to: {args.output}")
            except OSError as exc:
                print(f"Error writing markdown report: {exc}", file=sys.stderr)
                return 4
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
