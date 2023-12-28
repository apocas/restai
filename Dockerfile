FROM python:3.11

RUN useradd -m user

USER user
WORKDIR /app

COPY . /app

ENV ANONYMIZED_TELEMETRY=False

RUN pip install poetry
RUN poetry install --no-dev

EXPOSE 9000

CMD ["python", "main.py"]
