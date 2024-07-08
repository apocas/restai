FROM node:lts AS frontend-builder

WORKDIR /frontend

RUN git clone https://github.com/apocas/restai-frontend .

# Install dependencies and build
RUN npm i && npm run build

FROM nvidia/cuda:12.5.0-devel-ubuntu20.04 AS backend-builder

ARG WITH_GPU

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PIP_DEFAULT_TIMEOUT=100

# Install system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client python3-dev wget build-essential \
    zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev libbz2-dev \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install Python 3.11 from source
RUN wget https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz \
    && tar -xf Python-3.11.9.tgz \
    && cd Python-3.11.9 \
    && ./configure --enable-optimizations \
    && make -j $(nproc) \
    && make altinstall

# Update PATH
ENV PATH="/usr/local/bin/python3.11:$PATH"

# Install poetry
RUN curl -sSL https://install.python-poetry.org | python -
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Cache project files
COPY pyproject.toml poetry.lock /app/

# Install dependencies
RUN poetry install \
    $(if [ "$RESTAI_DEV" = 'production' ]; then echo '--without dev'; fi) \
    --no-interaction --no-ansi --no-root

RUN if [ "$WITH_GPU" = 'true' ]; then echo "Installing gpu deps" \
    && poetry install --with gpu 2>&1 > gpu.log || echo "This usually fails" \
    && echo "Installing flash_attn fix" \
    && poetry run pip install flash-attn==2.5.2 --no-build-isolation; fi

# Stripped down container for running the app, CPU support only
FROM python:3.11.9-slim AS cpu-runtime

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
FROM python:3.11.9-slim AS gpu-runtime

# We still need postgres libraries
RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Get ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

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

# GPU enabled runtime, use nvidia base images to avoid driver issues:
# https://hub.docker.com/r/nvidia/cuda/tags
FROM nvidia/cuda:11.6.1-runtime-ubuntu20.04 AS gpu-runtime-cuda

# We still need postgres libraries, and we will need to build python from source since the version shipped is 3.10
RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client wget build-essential \
    zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev libbz2-dev \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install Python 3.11 from source
RUN wget https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz \
    && tar -xf Python-3.11.9.tgz \
    && cd Python-3.11.9 \
    && ./configure --enable-optimizations \
    && make -j $(nproc) \
    && make altinstall

# Update PATH
ENV PATH="/usr/local/bin/python3.11:$PATH"

# Get ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

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
