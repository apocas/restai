.PHONY: start
start:
	uvicorn app.main:app --reload --port 9000

install:
	pip install -r requirements.txt

.PHONY: test
test:
	pytest tests