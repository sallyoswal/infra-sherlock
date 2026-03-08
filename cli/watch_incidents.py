"""CLI loop for automated incident watch and team notifications."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cli.env_utils import load_local_env
from incident_agent.watch import run_watch_loop

try:
    from rich.console import Console

    HAS_RICH = True
except Exception:
    HAS_RICH = False


def build_parser() -> argparse.ArgumentParser:
    """Build parser for watch mode."""
    parser = argparse.ArgumentParser(prog="infra-sherlock-watch")
    parser.add_argument("incidents", nargs="+", help="Incident names to watch")
    parser.add_argument(
        "--mode",
        choices=["local", "cloud"],
        required=True,
        help="Watch mode: local reads fixture datasets; cloud uses configured collectors only.",
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
        default=PROJECT_ROOT / "datasets" / "incidents",
        help="Path to incidents dataset root",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="Polling interval in seconds",
    )
    parser.add_argument(
        "--detect-and-notify",
        action="store_true",
        help="Run a single detection/notification cycle and exit.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--plugin-config",
        type=Path,
        default=PROJECT_ROOT / "config" / "plugins.yaml",
        help="Path to plugin config YAML",
    )
    parser.add_argument(
        "--routing-config",
        type=Path,
        default=PROJECT_ROOT / "config" / "routing.yaml",
        help="Path to routing config YAML",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=PROJECT_ROOT / "state" / "alerts.json",
        help="Path to notification state file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run cloud collectors: print what would be fetched without making cloud API calls.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run incident watch mode."""
    load_local_env(PROJECT_ROOT)
    args = build_parser().parse_args(argv)
    if args.once and not args.detect_and_notify:
        warnings.warn("--once is deprecated; use --detect-and-notify.", stacklevel=2)
    if args.dry_run:
        import os

        os.environ["PLUGIN_DRY_RUN"] = "1"
    if args.mode == "cloud" and not args.service_name:
        print("Error: --service-name is required when --mode cloud", file=sys.stderr)
        return 2
    run_once = args.detect_and_notify or args.once
    results = run_watch_loop(
        incidents=args.incidents,
        datasets_root=args.datasets_root,
        interval_seconds=args.interval_seconds,
        once=run_once,
        plugin_config_path=args.plugin_config,
        routing_config_path=args.routing_config,
        state_path=args.state_path,
        investigation_mode=args.mode,
        service_name=args.service_name,
        incident_title=args.incident_title,
    )

    if HAS_RICH:
        console = Console()
        for result in results:
            if result.error:
                console.print(f"[red]watch error[/red] {result.incident_name}: {result.error}")
            elif result.report:
                console.print(
                    f"[green]watch ok[/green] {result.incident_name} -> "
                    f"{result.report.service_name} ({result.report.confidence:.2f})"
                )
    else:
        for result in results:
            if result.error:
                print(f"watch error {result.incident_name}: {result.error}")
            elif result.report:
                print(f"watch ok {result.incident_name} -> {result.report.service_name} ({result.report.confidence:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
