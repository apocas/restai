# PHP example

A minimal RESTai client in two small classes plus a runnable demo.

- `Modem.php` — HTTP layer. Bearer **or** Basic auth, JSON in/out, TLS verification
  on by default, throws `RuntimeException` on non-2xx.
- `Project.php` — a project addressed by its integer **id**: `chat()`, `ask()`,
  `ingestText()`, `ingestUrl()`, `search()`, `edit()`, `delete()`, plus static
  `create()` / `find()`.
- `main.php` — full RAG lifecycle: discover models → ensure team → create project →
  ingest → ask → search → cleanup.

```bash
# Defaults to http://localhost:9000 with admin/admin
php main.php

# Or point it at your server with a scoped API key
RESTAI_URL="https://your-restai.com" RESTAI_API_KEY="sk-..." php main.php
```

Requires the `php-curl` extension. Configure at least one LLM and one embeddings
model in `/admin` first — the demo auto-discovers them.
