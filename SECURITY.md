# Security

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it privately:

- **Email**: petermdias@gmail.com
- **Subject**: `[SECURITY] RESTai — <brief description>`

Do not open a public GitHub issue. We will acknowledge within 48 hours.

---

## Security Features

### Authentication

- **Multiple auth methods**: JWT session cookies, Bearer API keys, and Basic auth
- **OAuth / SSO**: Google, Microsoft, GitHub, and generic OIDC providers — configure from the admin Settings page
- **LDAP**: Full LDAP/Active Directory integration with TLS support
- **Two-Factor Authentication (TOTP)**: Compatible with Google Authenticator, Authy, and other TOTP apps. Includes one-time recovery codes. Admins can enforce 2FA platform-wide.
- **Login rate limiting**: Database-backed brute-force protection that works across multiple workers

### Authorization & Access Control

- **Teams & RBAC**: Users belong to teams. Teams control access to projects, LLMs, embedding models, image generators, and audio generators. Users can belong to multiple teams.
- **Restricted users**: Read-only mode — restricted users can view assigned projects and use playgrounds but cannot create, edit, or delete resources
- **Project-level access**: Users are explicitly assigned to projects. Public projects can be shared within a team.
- **Per-project rate limiting**: Configurable requests-per-minute to prevent abuse and control costs
- **Admin impersonation**: Admins can impersonate any user for debugging, with full audit trail
- **Permissions matrix**: `GET /permissions/matrix` endpoint provides a complete view of who can access what

### Secrets & Encryption

- **Encryption at rest**: All sensitive credentials (API keys, bot tokens, database connection strings, sync source secrets) are encrypted in the database using Fernet symmetric encryption
- **Automatic masking**: Sensitive fields are masked in all API responses — credentials never leave the server in plaintext
- **TOTP secrets encrypted**: Two-factor authentication secrets are encrypted at rest with hashed recovery codes

### Input & Output Guards

- **Input guards**: Every user message can be checked against a configurable guard project before reaching the LLM. Guards use their own system prompt to evaluate content safety.
- **Output guards**: LLM responses can be checked after generation — block or warn on unsafe content
- **Guard modes**: Choose between hard-block (replace response with censorship message) or warn (flag but pass through)
- **Guard analytics**: Track block rates, view blocked requests, and monitor guard effectiveness over time via the built-in dashboard

### SSRF Protection

- URL ingestion and image resolution validate hostnames against private/internal network ranges before fetching
- Blocks access to loopback, RFC 1918, link-local, and IPv6 private addresses

### MCP Security

- **Command allowlist**: MCP stdio server commands are validated against a configurable allowlist (editable from the Settings page)
- **Shell injection prevention**: Arguments to MCP commands are checked for shell metacharacters
- **Domain validation**: The embeddable chat widget validates request origins against configured allowed domains, with automatic inclusion of the RESTai instance's own domain for admin previews

### CORS

- CORS headers are scoped exclusively to widget endpoints — all other API endpoints are same-origin only

### Audit Trail

- **Comprehensive audit logging**: Every mutation (create, update, delete) across the platform is automatically recorded with username, action, resource, status code, and timestamp
- **Admin-only access**: Audit logs are accessible via the admin dashboard with pagination and filtering
- **Tamper-resistant**: No API endpoint exists to modify or delete audit log entries

### API Key Management

- **Per-user API keys**: Users can create multiple API keys for programmatic access
- **Project-scoped keys**: Widget API keys are scoped to a single project with domain restrictions
- **Key rotation**: Keys can be regenerated without disrupting other keys
- **Hashed storage**: API keys are hashed for lookup — the plaintext is shown only once at creation

### Data Protection

- **Data retention policies**: Configurable automatic cleanup of old inference logs and audit entries
- **Token budget tracking**: Per-project token usage monitoring with cost analytics
- **Configurable logging**: Per-project toggle to disable inference logging for sensitive workloads

### Deployment Security

- **Docker**: Runs as non-root user, no secrets baked into images, health checks included
- **Kubernetes**: Helm chart with configurable secrets, supports fixed JWT/Fernet keys across replicas
- **Environment-based configuration**: All secrets via environment variables or the admin Settings page — never in code or config files

### Custom Branding & Isolation

- **Per-team branding**: Each team can have its own logo, colors, and app name — useful for multi-tenant deployments where different teams should not see each other's branding
- **Shadow DOM widget**: The embeddable chat widget uses Shadow DOM isolation to prevent style conflicts and XSS between the widget and the host page
