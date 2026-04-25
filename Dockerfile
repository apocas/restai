FROM node:lts AS frontend-builder

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build


FROM python:3.12 AS backend-builder

RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client python3-dev ffmpeg \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
# `--no-install-project` skips building the local workspace package
# (restai-core). Without it uv would try to build a wheel here and
# hatchling would need README.md + the package source — but we only
# copied pyproject.toml + uv.lock at this point on purpose, so we keep
# the dependency-install layer cacheable across source changes. The
# runtime runs `python main.py` directly from /app, so the package
# never needs to be importable as an installed dist anyway.
RUN uv sync --frozen --no-group gpu --no-group dev --no-install-project

COPY . /app


FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client ffmpeg \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

RUN useradd --user-group --system --create-home --no-log-init user \
    && mkdir -p /home/user/.cache /home/user/.local/share \
    && chown -R user:user /home/user

USER user
WORKDIR /app

COPY --from=frontend-builder /frontend/build /app/frontend/build
COPY --from=backend-builder --chown=user:user /app/.venv /app/.venv
COPY --chown=user:user . /app

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health/live')" || exit 1

CMD ["sh", "-c", ".venv/bin/python database.py && .venv/bin/python main.py"]
