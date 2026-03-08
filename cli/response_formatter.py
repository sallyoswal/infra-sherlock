"""Formatting and rendering helpers for incident chat UX."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from incident_agent.models import IncidentReport, TimelineEvent

ResponseIntent = Literal["summary", "root-cause", "timeline", "remediation", "evidence"]


@dataclass
class ResponsePayload:
    """Structured local response for a chat turn."""

    title: str
    lines: list[str]
    timeline: list[TimelineEvent] | None = None


def report_to_markdown(report: IncidentReport) -> str:
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


def short_time(ts: str) -> str:
    """Return HH:MM from an ISO timestamp when possible."""
    if "T" in ts and len(ts) >= 16:
        return ts[11:16]
    return ts


def _top_timeline_events(report: IncidentReport) -> list[TimelineEvent]:
    latest_deploy = next((e for e in reversed(report.timeline) if e.source == "deploy_history"), None)
    latest_infra = next((e for e in reversed(report.timeline) if e.source == "infra_changes"), None)
    first_error_log = next(
        (
            e
            for e in report.timeline
            if e.source == "logs" and ("ERROR" in e.event or "timeout" in e.event.lower())
        ),
        None,
    )

    selected: list[TimelineEvent] = []
    for item in (latest_deploy, latest_infra, first_error_log):
        if item and item not in selected:
            selected.append(item)

    if not selected:
        selected = report.timeline[:3]

    return sorted(selected, key=lambda e: e.timestamp)


def build_local_payload(report: IncidentReport, intent: ResponseIntent, detailed: bool = False) -> ResponsePayload:
    """Build concise or detailed local responses by conversational mode."""
    if intent == "summary":
        lines = [
            f"Most likely cause: {report.likely_root_cause}",
            f"Confidence: {report.confidence:.2f}",
        ]
        if detailed:
            lines.extend(["", "Top evidence:", *[f"- {e}" for e in report.key_evidence[:5]]])
        return ResponsePayload(title="Summary", lines=lines)

    if intent == "root-cause":
        lines = [
            report.likely_root_cause,
            f"Confidence: {report.confidence:.2f}",
        ]
        if detailed:
            lines.extend(["", "Why this is likely:", *[f"- {e}" for e in report.key_evidence[:4]]])
        return ResponsePayload(title="Root Cause", lines=lines)

    if intent == "evidence":
        lines = [f"- {e}" for e in report.key_evidence[:4]]
        if detailed:
            lines.extend(f"- {e}" for e in report.key_evidence[4:])
        return ResponsePayload(title="Evidence", lines=lines)

    if intent == "remediation":
        lines = [f"- {step}" for step in report.suggested_remediation]
        if detailed:
            lines.extend(["", "Next investigative steps:", *[f"- {s}" for s in report.next_investigative_steps]])
        return ResponsePayload(title="Remediation", lines=lines)

    # timeline
    chosen = report.timeline if detailed else _top_timeline_events(report)
    lines = [f"{short_time(e.timestamp)} {e.event}" for e in chosen]
    return ResponsePayload(title="Timeline", lines=lines, timeline=chosen)


def export_report_to_path(report: IncidentReport, target: Path) -> Path:
    """Write markdown report to target path and return resolved path."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report_to_markdown(report), encoding="utf-8")
    return target


class ChatRenderer:
    """Rich-aware renderer for a polished chat CLI experience."""

    def __init__(self) -> None:
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.table import Table

            self.console = Console()
            self.Panel = Panel
            self.Table = Table
            self.has_rich = True
        except Exception:
            self.console = None
            self.Panel = None
            self.Table = None
            self.has_rich = False

    def print_startup(self, report: IncidentReport, startup_summary: str | None = None) -> None:
        summary_lines = startup_summary.strip() if startup_summary else "\n".join(
            build_local_payload(report, intent="summary", detailed=False).lines
        )
        commands = "/summary  /root  /timeline  /evidence  /remediation  /help  /exit"
        banner = (
            "██╗███╗   ██╗███████╗██████╗  █████╗\n"
            "██║████╗  ██║██╔════╝██╔══██╗██╔══██╗\n"
            "██║██╔██╗ ██║█████╗  ██████╔╝███████║\n"
            "██║██║╚██╗██║██╔══╝  ██╔══██╗██╔══██║\n"
            "██║██║ ╚████║██║     ██║  ██║██║  ██║\n"
            "╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝\n"
            "\n"
            "███████╗██╗  ██╗███████╗██████╗ ██╗      ██████╗  ██████╗██╗  ██╗\n"
            "██╔════╝██║  ██║██╔════╝██╔══██╗██║     ██╔═══██╗██╔════╝██║ ██╔╝\n"
            "███████╗███████║█████╗  ██████╔╝██║     ██║   ██║██║     █████╔╝\n"
            "╚════██║██╔══██║██╔══╝  ██╔══██╗██║     ██║   ██║██║     ██╔═██╗\n"
            "███████║██║  ██║███████╗██║  ██║███████╗╚██████╔╝╚██████╗██║  ██╗\n"
            "╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝"
        )
        if not self.has_rich:
            print(banner)
            print("Infra Sherlock")
            print(f"Investigating incident: {report.incident_name}")
            print("")
            print("Summary:")
            print(summary_lines)
            print("")
            print(f"Commands: {commands}")
            return

        body = summary_lines
        self.console.print(f"[bold cyan]{banner}[/bold cyan]")
        self.console.print(self.Panel(body, title="Infra Sherlock", subtitle=f"Incident: {report.incident_name}", border_style="cyan"))
        self.console.print(f"[bold yellow]Commands:[/bold yellow] {commands}")

    def print_help(self) -> None:
        text = "Commands: /summary, /root, /timeline, /evidence, /remediation, /help, /exit, /export <file.md>"
        if self.has_rich:
            self.console.print(self.Panel(text, title="Help", border_style="green"))
        else:
            print(text)

    def print_payload(self, payload: ResponsePayload) -> None:
        if not self.has_rich:
            print(f"{payload.title.upper()}\n" + "\n".join(payload.lines))
            return

        if payload.title == "Timeline" and payload.timeline is not None:
            table = self.Table(title="Timeline", show_header=True, header_style="bold magenta")
            table.add_column("Time")
            table.add_column("Source")
            table.add_column("Event")
            for item in payload.timeline:
                table.add_row(short_time(item.timestamp), item.source, item.event)
            self.console.print(table)
            return

        body = "\n".join(payload.lines)
        self.console.print(self.Panel(body, title=payload.title.upper(), border_style="blue"))

    def print_llm_answer(self, answer: str) -> None:
        if self.has_rich:
            self.console.print(self.Panel(answer, title="Assistant", border_style="white"))
        else:
            print(answer)
