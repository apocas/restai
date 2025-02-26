FROM node:lts AS frontend-builder

WORKDIR /frontend

RUN git clone https://github.com/apocas/restai-frontend .

RUN npm install && npm run build




FROM python:3.11 as backend-builder

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true

# Install system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client python3-dev ffmpeg \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN curl -sSL https://install.python-poetry.org | python -
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY . /app

RUN poetry install




FROM python:3.11-slim as runtime

RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client ffmpeg \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

ENV ANONYMIZED_TELEMETRY=False \
    RESTAI_DEV=${RESTAI_DEV:-production}
    
RUN useradd --user-group --system --create-home --no-log-init user

RUN mkdir -p /home/user/.cache/ && chown -R user:user /home/user/.cache/
USER user

WORKDIR /app

RUN mkdir -p /home/user/.local/share
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/home/user/.local/bin:$PATH"

COPY --from=frontend-builder /frontend/build /app/frontend/build
COPY --from=backend-builder --chown=user:user /app/.venv /app/.venv

# there seems to be ownership issues with logs/ or .gitkeep file inside
COPY --chown=user:user . /app

EXPOSE 9001

CMD ["sh", "-c", ".venv/bin/python database.py && .venv/bin/python main.py"]
