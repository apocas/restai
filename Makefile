.PHONY: start
start:
	poetry run python main.py

#make remote host=user@1.2.3.4 path=/home/user/restai/
.PHONY: remote
remote:
	ssh -2 -L 5678:127.0.0.1:5678 $(host) "cd $(path); python3 -m debugpy --listen 127.0.0.1:5678 --wait-for-client main.py"

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
	poetry install -E gpu

.PHONY: installfix
installfix:
	$(echo $(poetry env info -p)/bin/pip3 install flash-attn==2.5.0 --no-build-isolation)

.PHONY: frontend
frontend:
	cd frontend && git pull && npm install && npm run build

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
