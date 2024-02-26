.PHONY: start
start:
	poetry run uvicorn app.main:app --port 9000 --workers 4

.PHONY: dev
dev:
	RESTAI_DEV=true uvicorn app.main:app --reload --port 9000

.PHONY: prod
prod:
	cd frontend && npm install && npm run build
	make start

.PHONY: install
install:
	poetry install
	git clone https://github.com/apocas/restai-frontend frontend
	cd frontend && npm install

.PHONY: installgpu
installgpu:
	poetry install --with gpu

.PHONY: installfix
installfix:
	$(echo $(poetry env info -p)/bin/pip3 install flash-attn==2.5.2 --no-build-isolation)

.PHONY: frontend
frontend:
	cd frontend && git pull && npm install && npm run build

.PHONY: docs
docs:
	poetry run python3 docs.py

.PHONY: test
test:
	pytest tests

.PHONY: code
code:
	autopep8 --in-place app/*.py

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
