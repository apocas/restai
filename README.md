<!-- markdownlint-disable MD033 -->

<h1 align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/restai-logo.png" alt="RestAI Logo"/>
  </br>RESTai
</h1>

<p align="center">
  <strong>AIaaS (AI as a Service) for everyone. Create AI projects and consume them using a simple REST API.</strong>
</p>

<h2 align="center">
  Demo: <a href="https://ai.ince.pt">https://ai.ince.pt</a> Username: <code>demo</code> Password: <code>demo</code>
</h2>

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/home.png"  alt="RESTai Home"/>
</div>

## Features

- **Projects**: There are multiple project types, each with its own features. ([rag](https://github.com/apocas/restai?tab=readme-ov-file#rag), [ragsql](https://github.com/apocas/restai?tab=readme-ov-file#ragsql), [inference](https://github.com/apocas/restai?tab=readme-ov-file#inference), [router](https://github.com/apocas/restai?tab=readme-ov-file#router), [agent](https://github.com/apocas/restai?tab=readme-ov-file#agent))
- **Teams**: Multi-tenancy layer. Each team has its own users, team admins, projects, and access to specific LLMs and embeddings. Projects belong to a team, and users can only use the models their team has been granted access to.
- **Users**: A user represents a user of the system. Users belong to one or more teams and may have access to multiple projects within those teams.
- **LLMs**: Supports any public LLM supported by LlamaIndex. Which includes any local LLM supported by Ollama, LiteLLM, etc.
- **API**: The API is a first-class citizen of RestAI. All endpoints are documented using [Swagger](https://apocas.github.io/restai/).
- **Frontend**: A React-based frontend is included in the `frontend/` folder and served automatically at `/admin`.
- **Image Generation**: Supports local and remote image generators. Local image generators are run in a separate process. New generators are [easily added](https://github.com/apocas/restai?tab=readme-ov-file#image-generators) and loaded dynamically.
- **Proxy**: Allows management of an OpenAI compatible proxy. LiteLLM is supported out of the box.
- **Telegram**: Connect any project to Telegram via BotFather. Messages are processed through the project's chat pipeline and responses are sent back automatically.

## Project Types

### RAG

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/rag.png" width="750" style="margin: 10px;"  alt="RESTai RAG"/>
</div>

- **Embeddings**: You may use any embeddings model supported by llamaindex. Check embeddings [definition](modules/embeddings.py).
- **Vectorstore**: There are two vectorstores supported: `ChromaDB` and `RedisVL`
- **Retrieval**: It features an embeddings search and score evaluator, which allows you to evaluate the quality of your embeddings and simulate the RAG process before the LLM. Reranking is also supported, ColBERT and LLM based.
- **Loaders**: You may use any loader supported by llamaindex.
- **Sandboxed mode**: RAG projects have "sandboxed" mode, which means that a locked default answer will be given when there aren't embeddings for the provided question. This is useful for chatbots, where you want to provide a default answer when the LLM doesn't know how to answer the question, reduncing hallucination.
- **Evaluation**: You may evaluate your RAG agent using [deepeval](https://github.com/confident-ai/deepeval). Using the `eval` property in the RAG endpoint.

### RAGSQL

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/ragsql.jpg" width="750"  style="margin: 10px;"/>
</div>

- **Connection**: Supply a MySQL or PostgreSQL connection string and it will automatically crawl the DB schema, using table and column names it’s able to figure out how to translate the question to sql and then write a response.

### Agent

- Zero-Shot ReAct Agents, specify which tools to use in the project and the agent will figure out how to use them to achieve the objective.
- New tools are easily added. Just create a new tool in the `tools` folder and it will be automatically picked up by RESTai. Check the `app/llms/tools` folder for examples using the builtin tools.

- **Tools**: Supply all the tools names you want the Agent to use in this project. (separated by commas)
- **Terminal**: Core tool that allows the agent to execute commands via SSH. (using [containerssh.io](https://containerssh.io) or similar is recommended)
- **MCP Servers**: Connect to external tool servers using the [Model Context Protocol](https://modelcontextprotocol.io). See [MCP Servers](#mcp-servers) below.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/agent1.png" width="40%"  style="margin: 10px;"/>
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/agent2.png" width="40%"  style="margin: 10px;"/>
</div>

#### MCP Servers

Agent projects can connect to external [MCP (Model Context Protocol)](https://modelcontextprotocol.io) servers to access additional tools. Two transport modes are supported:

##### HTTP/SSE

Connect to a remote MCP server over HTTP. Use the full URL as the host:

```
http://localhost:3001/sse
http://mcp-server.example.com/mcp
```

URLs ending in `/sse` use the SSE transport; all other HTTP URLs use the Streamable HTTP transport.

##### Stdio

Run a local MCP server as a subprocess. Enter the command as the host and provide arguments separately:

| Field | Example |
|-------|---------|
| Command | `npx` |
| Arguments | `-y @modelcontextprotocol/server-filesystem /tmp` |
| Env vars | `PORT=3001 DEBUG=true` |

Other stdio examples:

| Command | Arguments | Description |
|---------|-----------|-------------|
| `npx` | `-y @modelcontextprotocol/server-everything` | MCP reference test server |
| `npx` | `-y @modelcontextprotocol/server-filesystem /home/user/data` | Filesystem access |
| `python` | `-m mcp_server_sqlite --db-path /tmp/test.db` | SQLite access |
| `uvx` | `mcp-server-git --repository /path/to/repo` | Git repository tools |

##### Tool filtering

After adding a server, click **Check** to discover available tools. You can then select which tools the agent is allowed to use. Leaving the selection empty means all tools from that server are available.

##### API

MCP servers can also be configured via the API by including `mcp_servers` in the project options:

```json
{
  "options": {
    "mcp_servers": [
      {
        "host": "http://localhost:3001/sse",
        "tools": "tool1,tool2"
      },
      {
        "host": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        "env": {"HOME": "/home/user"},
        "tools": null
      }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `host` | string | URL for HTTP/SSE servers, or command name for stdio servers |
| `args` | list of strings | Arguments for stdio servers (optional) |
| `env` | object | Environment variables for stdio servers (optional) |
| `tools` | string or null | Comma-separated tool names to allow, or `null` for all tools |

You can probe an MCP server before saving it to discover available tools:

```bash
# HTTP server
curl -X POST http://localhost:9000/tools/mcp/probe \
  -H 'Content-Type: application/json' \
  -d '{"host": "http://localhost:3001/sse"}'

# Stdio server
curl -X POST http://localhost:9000/tools/mcp/probe \
  -H 'Content-Type: application/json' \
  -d '{"host": "npx", "args": ["-y", "@modelcontextprotocol/server-everything"]}'
```

### Inference

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/inference.png" width="750"  style="margin: 10px;"/>
</div>

- **Multimodal**: Inference projects support sending images alongside text in both question and chat modes. Use any vision-capable LLM (e.g. LLaVA, Gemini, GPT-4o) and pass an image as a base64 string or URL in the `image` field of the request body.

### Image Generators

- New generators are easily added. Just create a new tool in the `generators` folder and it will be automatically picked up by RESTai. Check the `app/image/workers` folder for examples using the builtin generators.
- **text2img**: RESTai supports txt2image like Stable Diffusion, Flux, DallE, ...
- **img2img**: RESTai supports img2img like BMBG2, ...

#### Flux1

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/flux1.png" width="50%"  style="margin: 10px;"/>
</div>

#### Stable Diffusion

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/vision_sd.png" width="25%"  style="margin: 10px;"/>
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/avatar.png" width="25%"  style="margin: 10px;"/>
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/rmbg2.png" width="25%"  style="margin: 10px;"/>
</div>


### Router

- Routes a message to the most suitable project. It's useful when you have multiple projects and you want to route the question to the most suitable one.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/router.png" width="750"  style="margin: 10px;"/>
</div>

- **Routes**: Very similar to Zero-Shot ReAct strategy, but each route is a project. The router will route the question to the project that has the highest score. It's useful when you have multiple projects and you want to route the question to the most suitable one.

## Telegram Integration

Connect your RESTai projects directly to Telegram. Any project of type **RAG**, **Inference**, or **Agent** can be linked to a Telegram bot.

### Setup

1. Create a bot using [BotFather](https://t.me/BotFather) on Telegram and copy the bot token.
2. In the project edit page, paste the token in the **Telegram Bot Token** field.
3. Save the project — RESTai will validate the token and start polling for messages automatically.

### How it works

- RESTai runs a background poller per project that long-polls the Telegram API for new messages.
- Incoming messages are processed through the project's standard chat pipeline (`chat_main`).
- Responses are sent back to the Telegram chat automatically (long messages are chunked to respect Telegram's 4096 character limit).
- Each Telegram user is identified by their `chat_id`, enabling per-user conversation history.
- Pollers start automatically on app startup for all projects with a configured token, and stop cleanly on shutdown.

## LLMs

- You may use any LLM provider supported by LlamaIndex.
- Builtin LLMs supported:
  - Ollama
  - OllamaMultiModal
  - OpenAI
  - OpenAILike (anything that is OpenAI compatible)
  - Grok
  - Groq
  - Anthropic
  - LiteLLM
  - vLLM
  - Gemini
  - AzureOpenAI

## Installation

- RESTai uses [uv](https://github.com/astral-sh/uv) to manage dependencies.

## Architecture

### Stateless

- Ideal scenario for production environments. There is no state stored in the RESTai service.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/restai_stateless.png" width="750"  style="margin: 10px;"/>
</div>

### Stateful

- Ideal for small deployments, direct interaction with the GPU layer.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/restai_stateful.png" width="750"  style="margin: 10px;"/>
</div>

## Development

- `make install`
- `make dev` (starts RESTai in development mode)

## Production

- `make install`
- `make start`

## Docker

- Edit the .env file accordingly
- `docker compose --env-file .env up --build`

You can specify profiles `docker compose --profile redis --profile mysql ....` to include additional components like the redis cache backend or a DB server, here are the supported profiles:

- `--profile redis` Starts and sets redis as the cache backend
- `--profile mysql` Starts and enables Mysql as the database server
- `--profile postgres` Starts and enables Postgres as the database server

The variables MYSQL_HOST and POSTGRES_HOST should match the names of the respective services "mysql" and "postgres" and not localhost or 127.0.0.1 when using the containers

To delete everything or a specific container don't forget to pass the necessary profiles to the compose command, EX:

- Removing everything
  `docker compose --profile mysql --profile postgres down --rmi all`
- Removing singular database volume
  `docker compose --profile mysql down --volumes`

*Note: the local_cache volume will also get removed since it's in the main service and not in any profile*

## Kubernetes

A Helm chart is provided in `chart/restai/` for deploying RestAI on Kubernetes.

### Quick Start

```bash
helm install restai chart/restai/ \
  --set config.database.postgres.host=my-postgres \
  --set secrets.postgresPassword=mypassword
```

### Prerequisites

RestAI requires a PostgreSQL database (recommended) or MySQL. Deploy these separately using your preferred method, for example:

```bash
helm install postgres oci://registry-1.docker.io/bitnamicharts/postgresql \
  --set auth.database=restai \
  --set auth.username=restai \
  --set auth.password=mypassword
```

Optional services:
- **Redis** — for persistent chat history across restarts (`config.redis.enabled=true`)
- **ChromaDB** — for RAG vector storage (`config.vectorStore.chromadb.host`)

### Production Configuration

For production and multi-replica deployments, you **must** set fixed application secrets. Without them, each pod generates random values which breaks JWT validation and API key encryption across pods and restarts.

```bash
helm install restai chart/restai/ \
  --set config.database.postgres.host=postgres \
  --set secrets.postgresPassword=mypassword \
  --set secrets.authSecret=$(openssl rand -base64 48) \
  --set secrets.ssoSecretKey=$(openssl rand -base64 48) \
  --set secrets.fernetKey=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
```

Or use a values file:

```yaml
# values-production.yaml
replicaCount: 3

config:
  database:
    postgres:
      host: postgres
      database: restai
      user: restai
  redis:
    enabled: true
    host: redis-master
    port: "6379"
  vectorStore:
    chromadb:
      host: chromadb
      port: "8000"

secrets:
  postgresPassword: "your-db-password"
  authSecret: "your-fixed-auth-secret"
  ssoSecretKey: "your-fixed-sso-secret"
  fernetKey: "your-fixed-fernet-key"
  defaultPassword: "change-me"
  openaiApiKey: "sk-..."

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: restai.example.com
      paths:
        - path: /
          pathType: ImplementationSpecific
  tls:
    - secretName: restai-tls
      hosts:
        - restai.example.com

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80

resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 2000m
    memory: 4Gi
```

```bash
helm install restai chart/restai/ -f values-production.yaml
```

### External Secret Management

If you manage secrets externally (e.g. HashiCorp Vault, Sealed Secrets, External Secrets Operator), use `existingSecret` to reference your own K8s Secret instead of having the chart create one:

```yaml
existingSecret: "my-restai-secrets"
```

Your secret must contain the expected environment variable keys (e.g. `RESTAI_AUTH_SECRET`, `POSTGRES_PASSWORD`, `OPENAI_API_KEY`, etc.).

### Health Checks

RestAI exposes two health endpoints used by the Helm chart for Kubernetes probes:

- `GET /health/live` — liveness probe, always returns 200 if the process is running
- `GET /health/ready` — readiness probe, checks database and Redis connectivity

## API

- **Endpoints**: All the API endpoints are documented and available at: [Endpoints](https://apocas.github.io/restai/api.html)
- **Swagger**: Swagger/OpenAPI documentation: [Swagger](https://apocas.github.io/restai/swagger/)

## Frontend

- The frontend is included in the `frontend/` folder (React 18 + MUI).
- `make install` automatically installs dependencies and builds it.
- In development, run `cd frontend && npm start` for a dev server on port 3000 (proxies API requests to port 9000).
- In production, the built frontend is served by the backend at `/admin`.

## Tests

- Tests are implemented using `pytest`. Run them with `make test`.

## License

Pedro Dias - [@pedromdias](https://twitter.com/pedromdias)

Licensed under the Apache license, version 2.0 (the "license"); You may not use this file except in compliance with the license. You may obtain a copy of the license at:

    http://www.apache.org/licenses/LICENSE-2.0.html

Unless required by applicable law or agreed to in writing, software distributed under the license is distributed on an "as is" basis, without warranties or conditions of any kind, either express or implied. See the license for the specific language governing permissions and limitations under the license.
