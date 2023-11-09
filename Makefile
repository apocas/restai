.PHONY: start
start:
	uvicorn app.main:app --reload --port 9000

.PHONY: prod
prod:
	uvicorn app.main:app --host 0.0.0.0 --port 9000

.PHONY: install
install:
	pip install -r requirements.txt

.PHONY: frontend
frontend:
	cd frontend && npm install && npm run build

.PHONY: docs
docs:
	python3 docs.py

.PHONY: test
test:
	pytest tests

.PHONY: clean
clean:
	rm -rf frontend/html/*

.PHONY: dockershell
dockershell:
	@docker run --rm -t -i -v $(shell pwd):/app restai bash

.PHONY: dockerbuild
dockerbuild:
	@docker build -t restai .

.PHONY: dockernpminstall
dockernpminstall:
	cd frontend && docker run --rm -t -i -v $(shell pwd):/app --workdir /app node:12.18.1 make frontend

.PHONY: dockernpmbuild
dockernpmbuild:
	cd frontend && docker run --rm -t -i -v $(shell pwd):/app --workdir /app node:12.18.1 make npmbuild
