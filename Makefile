.PHONY: start
start:
	uvicorn app.main:app --reload --port 9000

.PHONY: test
test:
	pytest tests