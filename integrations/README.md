# Integrations Skeleton

This folder is a placeholder layout for teams adopting Infra Sherlock in production.

Put organization-specific integration files in the provider folders below.
Typical files include API adapters, field-mapping specs, query templates, and auth notes.

Current placeholders:

- `integrations/aws/`
- `integrations/cloudtrail/`
- `integrations/datadog/`
- `integrations/pagerduty/`
- `integrations/pull_requests/`
- `integrations/terraform/`

Notes:

- This folder is intentionally scaffold-only.
- Runtime code in `incident_agent/plugins/` remains the active execution path.
- Keep secrets out of this repo; use env vars or your secret manager.
