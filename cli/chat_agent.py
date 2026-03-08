"""Interactive chat CLI for discussing a local incident with OpenAI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Support direct execution: `python cli/chat_agent.py ...`
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cli.env_utils import load_local_env
from incident_agent.chat import IncidentChatError, ask_incident_question, create_chat_session
from incident_agent.loader import IncidentDataError
from incident_agent.models import IncidentReport


def build_parser() -> argparse.ArgumentParser:
    """Build parser for interactive incident chat."""
    parser = argparse.ArgumentParser(prog="infra-sherlock-chat")
    parser.add_argument("incident_name", help="Incident scenario name")
    parser.add_argument(
        "--datasets-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "datasets" / "incidents",
        help="Path to incidents dataset root",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional OpenAI model override (defaults to OPENAI_MODEL or gpt-4o-mini).",
    )
    return parser


def _report_to_markdown(report: IncidentReport) -> str:
    """Convert an incident report into markdown."""
    lines: list[str] = [
        f"# {report.incident_title}",
        "",
        f"- **Incident Name:** `{report.incident_name}`",
        f"- **Service:** `{report.service_name}`",
        f"- **Likely Root Cause:** {report.likely_root_cause}",
        f"- **Confidence:** {report.confidence:.2f}",
        "",
        "## Key Evidence",
    ]
    lines.extend(f"- {item}" for item in report.key_evidence)
    lines.append("")
    lines.append("## Incident Timeline")
    lines.extend(f"- `{event.timestamp}` [{event.source}] {event.event}" for event in report.timeline)
    lines.append("")
    lines.append("## Suggested Remediation")
    lines.extend(f"- {item}" for item in report.suggested_remediation)
    lines.append("")
    lines.append("## Next Investigative Steps")
    lines.extend(f"- {item}" for item in report.next_investigative_steps)
    lines.append("")
    return "\n".join(lines)


def handle_slash_command(command: str, report: IncidentReport) -> str:
    """Handle local slash commands for fast incident navigation."""
    if command == "/summary":
        return (
            f"Incident: {report.incident_title} ({report.incident_name})\n"
            f"Service: {report.service_name}\n"
            f"Likely Root Cause: {report.likely_root_cause}\n"
            f"Confidence: {report.confidence:.2f}"
        )
    if command == "/timeline":
        lines = ["Incident Timeline:"]
        lines.extend(f"- {e.timestamp} [{e.source}] {e.event}" for e in report.timeline)
        return "\n".join(lines)
    if command == "/evidence":
        lines = ["Key Evidence:"]
        lines.extend(f"- {item}" for item in report.key_evidence)
        return "\n".join(lines)
    if command == "/remediation":
        lines = ["Suggested Remediation:"]
        lines.extend(f"- {item}" for item in report.suggested_remediation)
        return "\n".join(lines)
    if command.startswith("/export "):
        output_path = Path(command.split(" ", 1)[1].strip())
        if not output_path:
            return "Usage: /export <file.md>"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(_report_to_markdown(report), encoding="utf-8")
        return f"Exported report to: {output_path}"
    return "Unknown command. Use /summary, /timeline, /evidence, /remediation, /export <file.md>."


def main(argv: list[str] | None = None) -> int:
    """Start an interactive terminal chat for an incident."""
    load_local_env(PROJECT_ROOT)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        session = create_chat_session(
            incident_name=args.incident_name,
            datasets_root=args.datasets_root,
        )
    except (IncidentDataError, IncidentChatError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Infra Sherlock Chat: {session.report.incident_title} ({session.report.incident_name})")
    print("Ask questions about this incident. Type 'exit' or 'quit' to stop.")
    print("Slash commands: /summary, /timeline, /evidence, /remediation, /export <file.md>")
    while True:
        try:
            question = input("> ").strip()
        except EOFError:
            print()
            break
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue
        if question.startswith("/"):
            try:
                print(handle_slash_command(question, session.report))
            except OSError as exc:
                print(f"Error: failed to run command: {exc}", file=sys.stderr)
                return 4
            continue
        try:
            answer = ask_incident_question(session=session, question=question, model=args.model)
        except IncidentChatError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 3
        print(answer)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
