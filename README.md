# AI Infra First Responder

Local-first Python incident investigation agent that simulates an AI SRE/DevOps first responder.

It ingests deterministic local datasets (logs, metrics, deploy history, infra changes), correlates evidence, and outputs a recruiter-ready incident report with root cause, confidence, remediation, and timeline.

## Why This Project Matters

This project demonstrates practical incident response engineering without requiring cloud accounts or vendor integrations. It showcases skills relevant to Security, DevOps, SRE, and backend engineering interviews:

- structured observability analysis
- incident correlation and root-cause reasoning
- clean Python architecture and testability
- CLI-first operator workflow

## Architecture

Core flow:

1. `agent.py` orchestrates investigation.
2. Tool modules parse and summarize each signal type.
3. Deterministic reasoner applies explicit heuristics.
4. CLI prints a polished report (with `rich` if installed).

Design choices:

- deterministic v1: no API key or network calls required
- small, typed modules with clear interfaces
- dataclass-based report model for stable outputs

## Repository Layout

```text
.
├── .env.example
├── README.md
├── requirements.txt
├── cli/
│   └── run_agent.py
├── datasets/
│   └── incidents/
│       └── payments_db_timeout/
│           ├── deploy_history.json
│           ├── infra_changes.json
│           ├── logs.jsonl
│           ├── metadata.json
│           └── metrics.csv
├── incident_agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── loader.py
│   ├── models.py
│   ├── reasoning/
│   │   └── deterministic_reasoner.py
│   └── tools/
│       ├── deploy_tool.py
│       ├── infra_tool.py
│       ├── logs_tool.py
│       └── metrics_tool.py
└── tests/
    ├── test_agent_flow.py
    ├── test_cli.py
    ├── test_deploy_tool.py
    ├── test_infra_tool.py
    ├── test_logs_tool.py
    ├── test_metrics_tool.py
    └── test_reasoner.py
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python cli/run_agent.py investigate payments_db_timeout
```

## Demo Output (Example)

- Incident title and service
- likely root cause with confidence score
- key evidence bullets from logs/metrics/deploy/infra
- timeline of deploy + infra changes + symptom onset
- remediation actions
- next investigative steps

## Testing

```bash
pytest -q
```

## Roadmap

- Add optional `llm_reasoner.py` when `OPENAI_API_KEY` is present.
- Add markdown report export (`--output report.md`).
- Add additional incident scenarios (e.g. cache stampede, DNS misroute).
- Add MCP server wrapper for tool-based assistant integration.
