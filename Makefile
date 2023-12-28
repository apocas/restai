.PHONY: start
start:
	uvicorn app.main:app --host 0.0.0.0 --port 9000

.PHONY: devfrontend
devfrontend:
	cd frontend && REACT_APP_RESTAI_API_URL=http://127.0.0.1:9000 npm run start

.PHONY: dev
dev:
	RESTAI_DEV=true uvicorn app.main:app --reload --port 9000

.PHONY: prod
prod:
	cd frontend && npm install && npm run build
	make start

.PHONY: install
install:
	cd frontend && npm install
	poetry install

.PHONY: installgpu
installgpu:
	poetry install -E gpu

.PHONY: frontend
frontend:
	cd frontend && npm install && npm run build

.PHONY: docs
docs:
	python3 docs.py

.PHONY: test
test:
	pytest tests

.PHONY: code
codestyle:
	autopep8 --in-place app/*.py

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
