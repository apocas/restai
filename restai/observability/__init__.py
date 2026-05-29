"""Operational visibility: audit trail, telemetry, cron logging, instance id.

Groups the observability concerns that were loose top-level modules:

- `audit` — request audit middleware + `_log_to_db` for security-relevant
  actions (impersonation, settings changes, auth events).
- `telemetry` — anonymous usage telemetry loop.
- `cron_log` — `CronLogger` DB-backed per-job run logging (heavily used by
  every `crons/*.py`).
- `instance` — stable per-deployment instance id (used to label containers
  and tag telemetry).

`telemetry` reads `instance.get_instance_id` (intra-package); the rest are
independent. All DB/config imports inside these modules are function-local,
so packaging them introduces no import-time edges.
"""
