.PHONY: start

build:
	@docker build -t restai .

shell:
	@docker run --rm -t -i -v $(shell pwd):/app restai bash

start:
	uvicorn app.main:app --reload --port 9000

.PHONY: install
install:
	pip install -r requirements.txt

.PHONY: frontend
frontend:
	cd frontend && npm install && npm run build

.PHONY: npmbuild
npmbuild:
	cd frontend && npm run build

.PHONY: dockernpminstall
dockernpminstall:
	cd frontend && docker run --rm -t -i -v $(shell pwd):/app --workdir /app node:12.18.1 make frontend

.PHONY: dockernpmbuild
dockernpmbuild:
	cd frontend && docker run --rm -t -i -v $(shell pwd):/app --workdir /app node:12.18.1 make npmbuild

.PHONY: docs
docs:
	python3 docs.py

.PHONY: test
test:
	pytest tests
