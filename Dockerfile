FROM python:3.11

ENV ANONYMIZED_TELEMETRY=False

RUN useradd --user-group --system --create-home --no-log-init user
USER user

WORKDIR /app
COPY . /app

RUN mkdir -p /home/user/.local/share
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/home/user/.local/bin:$PATH"

RUN poetry install

EXPOSE 9000

CMD ["python", "main.py"]
