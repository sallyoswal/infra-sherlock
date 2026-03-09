"""Interactive chat CLI for discussing incidents with Infra Sherlock."""
# ruff: noqa: E402

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
    export_report_to_path,
)
from incident_agent.chat import IncidentChatError, ask_incident_question, create_chat_session
from incident_agent.loader import IncidentDataError
from incident_agent.llm_provider import get_provider, has_llm_credentials
from incident_agent.models import IncidentReport


def build_parser() -> argparse.ArgumentParser:
    """Build parser for interactive incident chat."""
    parser = argparse.ArgumentParser(prog="infra-sherlock-chat")
    parser.add_argument("incident_name", help="Incident scenario name")
    parser.add_argument(
        "--mode",
        choices=["local", "cloud"],
        default="local",
        help="Chat mode: local reads fixture datasets; cloud uses configured collectors only.",
    )
    parser.add_argument(
        "--service-name",
        type=str,
        default=None,
        help="Required in cloud mode: service identifier used by cloud collectors.",
    )
    parser.add_argument(
        "--incident-title",
        type=str,
        default=None,
        help="Optional in cloud mode: incident title override for generated reports.",
    )
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
    """Backward-compatible command helper used by tests and automation.

    In AI-only mode, slash commands are translated into focused prompts.
    """
    if command == "/summary":
        return "Summarize this incident in 2-4 lines for an on-call engineer."
    if command in {"/root", "/root-cause"}:
        return "What is the most likely root cause? Keep it to 2-4 lines."
    if command == "/timeline":
        return "Show the incident timeline as concise bullet points with timestamps."
    if command == "/evidence":
        return "List the strongest evidence supporting the current root-cause hypothesis."
    if command == "/remediation":
        return "Give the top remediation actions in priority order."
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

    if not has_llm_credentials():
        print(
            f"Error: AI-only chat mode requires LLM credentials (provider={get_provider()}).",
            file=sys.stderr,
        )
        return 3
    if args.mode == "cloud" and not args.service_name:
        print("Error: --service-name is required when --mode cloud", file=sys.stderr)
        return 2

    try:
        session = create_chat_session(
            incident_name=args.incident_name,
            datasets_root=args.datasets_root,
            investigation_mode=args.mode,
            service_name=args.service_name,
            incident_title=args.incident_title,
        )
    except (IncidentDataError, IncidentChatError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    renderer = ChatRenderer()
    try:
        startup_summary = ask_incident_question(
            session=session,
            question="Give a concise startup overview: what happened, likely cause, and confidence in 2-4 lines.",
            model=args.model,
            concise=True,
            focus_mode="summary",
        )
    except IncidentChatError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3
    renderer.print_startup(session.report, startup_summary=startup_summary)

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
            if command_output.startswith("Exported report"):
                renderer.print_llm_answer(command_output)
                continue
            if command_output.startswith("Unknown command"):
                renderer.print_llm_answer(command_output)
                continue
            try:
                answer = ask_incident_question(
                    session=session,
                    question=command_output,
                    model=args.model,
                    concise=True,
                    focus_mode=user_text.lstrip("/"),
                )
            except IncidentChatError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 3
            renderer.print_llm_answer(answer)
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
