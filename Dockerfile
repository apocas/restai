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
RUN uv sync --frozen --no-group gpu --no-group dev --no-editable

COPY . /app


FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client ffmpeg \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

ENV ANONYMIZED_TELEMETRY=False

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
