"""CLI launcher for Infra Sherlock MCP server."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from incident_agent.mcp.server import run_stdio_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="infra-sherlock-mcp")
    parser.add_argument(
        "--datasets-root",
        type=Path,
        default=PROJECT_ROOT / "datasets" / "incidents",
        help="Path to incidents dataset root",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_stdio_server(datasets_root=args.datasets_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
