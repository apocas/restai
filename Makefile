.PHONY: start
start:
	poetry run uvicorn restai.main:app --port 9000 --workers 4

.PHONY: database
database:
	poetry run python database.py

.PHONY: frontend
frontend:
	cd frontend && git pull && npm install && npm run build

.PHONY: dev
dev:
	RESTAI_DEV=true uvicorn restai.main:app --reload --port 9000

.PHONY: build
build:
	poetry build

.PHONY: install
install:
	poetry install
	make database
	git clone https://github.com/apocas/restai-frontend frontend
	make frontend

.PHONY: installgpu
installgpu:
	poetry install --with gpu
	poetry run python3 download.py

.PHONY: docs
docs:
	poetry run python3 docs.py

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
