# Infra Sherlock

Local-first Python incident investigation agent that simulates an AI SRE/DevOps incident investigator.

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
3. Timeline reconstruction merges timestamped events from logs, deploy history, and infra changes.
4. If LLM credentials are configured (`openai` or `openrouter`), `llm_reasoner.py` synthesizes a strict JSON report.
5. If LLM mode is unavailable/fails, deterministic fallback reasoner applies explicit heuristics.
6. CLI prints a polished report (with `rich` if installed).

Design choices:

- local-first by default: no API key or network calls required
- small, typed modules with clear interfaces
- dataclass-based report model for stable outputs
- strict report schema validation even in LLM mode

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
│   ├── mcp/
│   │   └── wrapper.py
│   ├── models.py
│   ├── reasoning/
│   │   ├── deterministic_reasoner.py
│   │   ├── fallback_reasoner.py
│   │   └── llm_reasoner.py
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

# Optional: export markdown report
python cli/run_agent.py investigate payments_db_timeout --output reports/payments_db_timeout.md
```

## Incident Chat

Use an interactive chat session for follow-up questions about a specific incident:

```bash
python cli/chat_agent.py payments_db_timeout
```

Notes:
- Requires LLM credentials in your local environment or `.env` (`openai` or `openrouter`).
- Chat uses the locally generated incident report as context.
- Type `exit` or `quit` to end the session.
- Built-in local slash commands:
  - `/summary`
  - `/timeline`
  - `/evidence`
  - `/remediation`
  - `/export <file.md>`

## Optional LLM Mode

If LLM credentials are set, the agent attempts LLM synthesis for the final report and enforces a strict response schema before constructing `IncidentReport`.

If the key is missing, the `openai` package is unavailable, or the LLM response is invalid, the workflow automatically falls back to deterministic reasoning.

You can keep secrets local by creating a `.env` file (already gitignored):

```bash
cp .env.example .env
# then set one provider block in .env:
# LLM_PROVIDER=openai with OPENAI_API_KEY
# or LLM_PROVIDER=openrouter with OPENROUTER_API_KEY
```

## Minimal MCP Wrapper

The project now includes a lightweight MCP-compatible wrapper that keeps the existing CLI intact and avoids any hard MCP SDK dependency.

- Tool metadata: `incident_agent.mcp.wrapper.get_investigate_tool_spec()`
- Tool function: `incident_agent.mcp.wrapper.investigate_incident_tool(incident_name=...)`

Example:

```python
from incident_agent.mcp.wrapper import investigate_incident_tool

result = investigate_incident_tool("payments_db_timeout")
print(result["likely_root_cause"])
```

This returns a JSON-safe dictionary matching the `IncidentReport` schema, so it can be directly exposed through an MCP server later.

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

- Add a second CLI entrypoint (`infra-sherlock`) via packaging.
- Add additional incident scenarios (e.g. cache stampede, DNS misroute).
- Add full MCP server process (transport/auth/tool registration runtime).
