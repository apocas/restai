"""External service integrations and protocol bridges.

Groups the modules that connect RESTai to outside systems or expose it over
extra protocols, previously loose at top level:

- `oauth` — SSO providers (Google/Microsoft/GitHub/OIDC) via Authlib.
- `mcp` — internal MCP server exposing projects as MCP tools.
- `direct_access` — team/usage resolution for the direct image/audio APIs.
- `sync` — knowledge-base sync sources (URL/S3/Confluence/SharePoint/Drive).
- `knowledge_graph` — entity extraction + graph build/query over RAG docs.

`sync` calls `knowledge_graph.extract_and_persist` (intra-package, deferred).
Cohesion here is looser than the other packages — these are grouped as
"things that talk to the outside world" rather than a single subsystem.
"""
