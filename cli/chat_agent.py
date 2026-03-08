"""Interactive chat CLI for discussing incidents with Infra Sherlock."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Support direct execution: `python cli/chat_agent.py ...`
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cli.env_utils import load_local_env
from cli.response_formatter import (
    ChatRenderer,
    build_local_payload,
    export_report_to_path,
)
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
        help="Optional provider model override.",
    )
    return parser


def handle_slash_command(command: str, report: IncidentReport) -> str:
    """Backward-compatible command helper used by tests and automation."""
    if command == "/summary":
        payload = build_local_payload(report, intent="summary")
        return "\n".join(payload.lines)
    if command in {"/root", "/root-cause"}:
        payload = build_local_payload(report, intent="root-cause")
        return "\n".join(payload.lines)
    if command == "/timeline":
        payload = build_local_payload(report, intent="timeline", detailed=True)
        return "Incident Timeline:\n" + "\n".join(
            f"- {item.timestamp} [{item.source}] {item.event}" for item in payload.timeline or []
        )
    if command == "/evidence":
        payload = build_local_payload(report, intent="evidence")
        return "Key Evidence:\n" + "\n".join(payload.lines)
    if command == "/remediation":
        payload = build_local_payload(report, intent="remediation")
        return "Suggested Remediation:\n" + "\n".join(payload.lines)
    if command.startswith("/export "):
        output_path = Path(command.split(" ", 1)[1].strip())
        export_report_to_path(report, output_path)
        return f"Exported report to: {output_path}"
    if command == "/help":
        return "Commands: /summary, /root, /timeline, /evidence, /remediation, /help, /exit"
    return "Unknown command. Use /help for available commands."


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

    renderer = ChatRenderer()
    renderer.print_startup(session.report)

    while True:
        try:
            user_text = input("> ").strip()
        except EOFError:
            print()
            break

        if user_text.lower() in {"exit", "quit", "/exit", "/quit"}:
            break
        if not user_text:
            continue

        if user_text.startswith("/export "):
            try:
                target = Path(user_text.split(" ", 1)[1].strip())
                export_report_to_path(session.report, target)
                renderer.print_llm_answer(f"Exported report to: {target}")
            except OSError as exc:
                print(f"Error: failed to export report: {exc}", file=sys.stderr)
                return 4
            continue

        if user_text.lower() in {"/help", "help"}:
            renderer.print_help()
            continue

        if user_text.startswith("/"):
            command_output = handle_slash_command(user_text, session.report)
            if command_output.startswith("Unknown command"):
                renderer.print_llm_answer(command_output)
                continue
            # Keep compatibility with existing slash command behavior.
            if user_text.lower() in {"/summary", "/root", "/root-cause", "/timeline", "/evidence", "/remediation"}:
                if user_text.lower() in {"/summary"}:
                    renderer.print_payload(build_local_payload(session.report, intent="summary"))
                elif user_text.lower() in {"/root", "/root-cause"}:
                    renderer.print_payload(build_local_payload(session.report, intent="root-cause"))
                elif user_text.lower() in {"/timeline"}:
                    renderer.print_payload(build_local_payload(session.report, intent="timeline", detailed=True))
                elif user_text.lower() in {"/evidence"}:
                    renderer.print_payload(build_local_payload(session.report, intent="evidence"))
                elif user_text.lower() in {"/remediation"}:
                    renderer.print_payload(build_local_payload(session.report, intent="remediation"))
                continue
            renderer.print_llm_answer("Unknown command. Use /help for available commands.")
            continue

        wants_detail = any(
            token in user_text.lower()
            for token in ("detail", "detailed", "explain", "deep", "deeper", "expand", "elaborate")
        )

        try:
            answer = ask_incident_question(
                session=session,
                question=user_text,
                model=args.model,
                concise=not wants_detail,
                focus_mode=None,
            )
        except IncidentChatError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 3

        renderer.print_llm_answer(answer)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
