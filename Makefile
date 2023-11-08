.PHONY: start
start:
	uvicorn app.main:app --reload --port 9000

install:
	pip install -r requirements.txt

frontend:
	cd frontend && npm install && npm run build

.PHONY: test
test:
	pytest tests