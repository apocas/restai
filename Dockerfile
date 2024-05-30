FROM node:lts AS frontend-builder

WORKDIR /frontend

RUN git clone https://github.com/apocas/restai-frontend .

# Install dependencies and build
RUN npm ci && npm run build

FROM python:3.11 as backend-builder

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true

# Install system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client python3-dev \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN curl -sSL https://install.python-poetry.org | python -
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Cache project files
COPY pyproject.toml poetry.lock /app/

# Install dependencies
RUN poetry install \
    $(if [ "$RESTAI_DEV" = 'production' ]; then echo '--without dev'; fi) \
    #$(if "$WITH_GPU"; then echo ' --with gpu'; fi) \
    --no-interaction --no-ansi --no-root

# Stripped down container for running the app
FROM python:3.11-slim as runtime

ENV ANONYMIZED_TELEMETRY=False \
    RESTAI_DEV=${RESTAI_DEV:-production}
    
RUN useradd --user-group --system --create-home --no-log-init user
USER user

WORKDIR /app

RUN mkdir -p /home/user/.local/share
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/home/user/.local/bin:$PATH"

# Copy the built frontend from previous stage
COPY --from=frontend-builder /frontend/html /app/frontend/html
COPY --from=backend-builder --chown=user:user /app/.venv /app/.venv

# there seems to be ownership issues with logs/ or .gitkeep file inside
COPY --chown=user:user . /app

EXPOSE 9000

CMD ["sh", "-c", ".venv/bin/python database.py && .venv/bin/python main.py"]
