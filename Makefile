.PHONY: start
start:
	uv run --no-group gpu uvicorn restai.main:app --port 9000 --workers 4

.PHONY: database
database:
	uv run --no-group gpu database.py

.PHONY: frontend
frontend:
	git clone https://github.com/apocas/restai-frontend frontend
	make frontend

.PHONY: dev
dev:
	RESTAI_DEV=true uvicorn restai.main:app --reload --port 9000

.PHONY: build
build:
	uv build

.PHONY: install
install:
	uv sync --no-group gpu
	bash install_cudnn_env.sh
	make database

.PHONY: installgpu
installgpu:
	uv sync
	uv run --no-group gpu download.py

.PHONY: migrate
migrate:
	uv run --no-group gpu migrate.py upgrade

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
