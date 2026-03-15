FROM node:lts AS frontend-builder

WORKDIR /frontend

RUN git clone https://github.com/apocas/restai-frontend .

RUN npm install && npm run build


FROM python:3.11 AS backend-builder

# Install system dependencies needed for compilation
RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client python3-dev ffmpeg \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (without gpu and dev groups)
RUN uv sync --frozen --no-group gpu --no-group dev --no-editable

# Copy source
COPY . /app


FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client ffmpeg \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

ENV ANONYMIZED_TELEMETRY=False

RUN useradd --user-group --system --create-home --no-log-init user
RUN mkdir -p /home/user/.cache/ && chown -R user:user /home/user/.cache/

USER user
WORKDIR /app

RUN mkdir -p /home/user/.local/share

COPY --from=frontend-builder /frontend/build /app/frontend/build
COPY --from=backend-builder --chown=user:user /app/.venv /app/.venv
COPY --chown=user:user . /app

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health/live')" || exit 1

CMD ["sh", "-c", ".venv/bin/python database.py && .venv/bin/python main.py"]
