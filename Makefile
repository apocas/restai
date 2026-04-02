-include .env
export

.PHONY: start
start:
	uv run --no-group gpu uvicorn restai.main:app --host $${RESTAI_HOST:-127.0.0.1} --port $${RESTAI_PORT:-9000} --workers $${RESTAI_WORKERS:-4}

.PHONY: database
database:
	uv run --no-group gpu database.py

.PHONY: frontend
frontend:
	cd frontend && npm install
	cd frontend && npm run build

.PHONY: dev
dev:
	RESTAI_DEV=true uvicorn restai.main:app --reload --host $${RESTAI_HOST:-127.0.0.1} --port $${RESTAI_PORT:-9000}

.PHONY: build
build:
	uv build

.PHONY: install
install:
	mkdir -p frontend/build
	uv sync --no-group gpu
	make database
	make frontend
	@if command -v nvidia-smi > /dev/null 2>&1 && nvidia-smi > /dev/null 2>&1; then \
		echo "GPU detected, running installgpu..."; \
		$(MAKE) installgpu; \
	fi

.PHONY: installgpu
installgpu:
	uv sync
	make envs
	uv run --no-group gpu download.py

.PHONY: envs
envs:
	bash worker_envs/install.sh

.PHONY: migrate
migrate:
	uv run --no-group gpu migrate.py upgrade

.PHONY: update
update:
	@echo "Fetching latest release from GitHub..."
	@LATEST=$$(git ls-remote --tags --sort=-v:refname origin 'refs/tags/v*' 2>/dev/null | head -1 | sed 's/.*refs\/tags\///'); \
	if [ -z "$$LATEST" ]; then \
		echo "No release tags found. Pulling latest from current branch..."; \
		git pull; \
	else \
		echo "Latest release: $$LATEST"; \
		git fetch --tags; \
		git checkout "$$LATEST"; \
	fi
	@echo "Installing dependencies..."
	uv sync --no-group gpu
	@echo "Running database migrations..."
	$(MAKE) migrate
	@echo "Building frontend..."
	$(MAKE) frontend
	@if command -v nvidia-smi > /dev/null 2>&1 && nvidia-smi > /dev/null 2>&1; then \
		echo "GPU detected, syncing GPU deps..."; \
		$(MAKE) installgpu; \
	fi
	@echo "Update complete."

.PHONY: docs
docs:
	uv run --no-group gpu docs.py

.PHONY: test
test:
	pytest tests

.PHONY: code
code:
	black app/*.py

.PHONY: clean
clean:
	rm -rf frontend

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
