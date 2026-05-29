"""Inference gates and resource-limit policy.

Groups the cross-cutting checks that run before/around inference and the
periodic cleanup, previously loose top-level modules:

- `budget` — per-project budget + rate limit + per-API-key monthly quota
  checks (raise 402/429), plus token accounting.
- `guard` — input/output guard projects (content moderation via a guard LLM).
- `retention` — knowledge/inference retention cleanup.

None import each other; this package is organizational. `budget` and `guard`
sit above `database`/`project`/`brain` (which stay at top level), so there is
no import cycle back into the core.
"""
