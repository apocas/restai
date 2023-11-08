FROM python:3.11

RUN useradd -m user

USER user
WORKDIR /app

COPY . /app

RUN pip install -r requirements.txt

EXPOSE 9000

CMD ["python", "main.py"]
