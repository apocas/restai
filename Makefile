.PHONY: start
start:
	poetry run uvicorn app.main:app --port 9000 --workers 4

.PHONY: database
database:
	poetry run python database.py

.PHONY: frontend
frontend:
	cd frontend && git pull && npm install && npm run build

.PHONY: dev
dev:
	RESTAI_DEV=true uvicorn app.main:app --reload --port 9000

.PHONY: install
install:
	poetry install
	make database
	git clone https://github.com/apocas/restai-frontend frontend
	make frontend

.PHONY: installgpu
installgpu:
	poetry install --with gpu

.PHONY: installfix
installfix:
	$(echo $(poetry env info -p)/bin/pip3 install flash-attn==2.5.2 --no-build-isolation)

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

# Set default values for DOCKER_PROFILES if not provided
DOCKER_PROFILES ?= cpu

.PHONY: dockershell
dockershell:
	@docker exec -it restai-restai-$(DOCKER_PROFILES)-1 bash

.PHONY: dockerpostgresql
dockerbuild:
	@docker compose --profile redis --profile postgres --env-file .env up --build -d

.PHONY: dockermysql
dockerbuild:
	@docker compose --profile redis --profile mysql --env-file .env up --build -d

.PHONY: dockerrmall
dockerbuild:
	@docker compose --profile redis --profile mysql --profile postgres --profile cpu --profile gpu down --rmi all
