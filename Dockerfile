FROM node:lts AS frontend-builder

WORKDIR /frontend

RUN git clone https://github.com/apocas/restai-frontend .

# Install dependencies and build
RUN npm i && npm run build

FROM python:3.11 as backend-builder

ARG WITH_GPU

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
    $(if [ "$WITH_GPU" = 'true' ]; then echo ' --with gpu'; fi) \
    --no-interaction --no-ansi --no-root

# Install pytorch with cuda if WITH_GPU is true
# https://pytorch.org/get-started/locally/
#RUN if [ "$WITH_GPU" = 'true' ]; then echo "Installing cuda enable torch" \
#    && poetry run pip install --upgrade --no-deps --force-reinstall torch --index-url https://download.pytorch.org/whl/cu118; fi

# Stripped down container for running the app, CPU support only
FROM python:3.11-slim as cpu-runtime

# We still need postgres libraries
RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

ENV ANONYMIZED_TELEMETRY=False \
    RESTAI_DEV=${RESTAI_DEV:-production}
    
RUN useradd --user-group --system --create-home --no-log-init user
# Create our cache directory and set permissions
RUN mkdir -p /home/user/.cache/ && chown -R user:user /home/user/.cache/
USER user

WORKDIR /app

# Copy the built frontend from previous stage
COPY --from=frontend-builder /frontend/html /app/frontend/html
COPY --from=backend-builder --chown=user:user /app/.venv /app/.venv

# there seems to be ownership issues with logs/ or .gitkeep file inside
COPY --chown=user:user . /app

EXPOSE 9001

CMD ["sh", "-c", ".venv/bin/python database.py && .venv/bin/python main.py"]

# GPU enabled runtime

FROM python:3.11 as gpu-runtime

# We still need postgres libraries
RUN apt-get update && apt-get install --no-install-recommends -y python3 postgresql-client \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

ENV ANONYMIZED_TELEMETRY=False \
    RESTAI_DEV=${RESTAI_DEV:-production}

RUN useradd --user-group --system --create-home --no-log-init user
# Create our cache directory and set permissions
RUN mkdir -p /home/user/.cache/ && chown -R user:user /home/user/.cache/
USER user

WORKDIR /app

# Copy the built frontend from previous stage
COPY --from=frontend-builder /frontend/html /app/frontend/html
COPY --from=backend-builder --chown=user:user /app/.venv /app/.venv

# There seems to be ownership issues with logs/ or .gitkeep file inside
COPY --chown=user:user . /app

EXPOSE 9000

USER root

CMD ["tail", "-f", "/dev/null"]
#CMD ["sh", "-c", ".venv/bin/python database.py && .venv/bin/python main.py"]
