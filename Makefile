.PHONY: start
start:
	uvicorn app.main:app --reload --port 9000

.PHONY: install
install:
	pip install -r requirements.txt

.PHONY: frontend
frontend:
	cd frontend && npm install && npm run build

.PHONY: test
test:
	pytest tests