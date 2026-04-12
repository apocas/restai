-include .env
export

.PHONY: start
start:
	uv run --no-group gpu uvicorn restai.main:app --host $${RESTAI_HOST:-127.0.0.1} --port $${RESTAI_PORT:-9000} --workers $${RESTAI_WORKERS:-2}

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
	@echo ""
	@echo "=== Installation complete ==="
	@echo ""
	@read -p "Install RESTai as a systemd service? [y/N] " answer; \
	if [ "$$answer" = "y" ] || [ "$$answer" = "Y" ]; then \
		$(MAKE) systemd; \
	fi
	@read -p "Install cron jobs (sync + telegram + docker cleanup)? [y/N] " answer; \
	if [ "$$answer" = "y" ] || [ "$$answer" = "Y" ]; then \
		$(MAKE) cron; \
	fi

.PHONY: systemd
systemd:
	@RESTAI_DIR=$$(pwd); \
	RESTAI_USER=$$(whoami); \
	RESTAI_UV=$$(which uv); \
	echo "[Unit]" > /tmp/restai.service; \
	echo "Description=RESTai AI Platform" >> /tmp/restai.service; \
	echo "After=network.target" >> /tmp/restai.service; \
	echo "" >> /tmp/restai.service; \
	echo "[Service]" >> /tmp/restai.service; \
	echo "Type=simple" >> /tmp/restai.service; \
	echo "User=$$RESTAI_USER" >> /tmp/restai.service; \
	echo "WorkingDirectory=$$RESTAI_DIR" >> /tmp/restai.service; \
	echo "EnvironmentFile=$$RESTAI_DIR/.env" >> /tmp/restai.service; \
	echo "ExecStart=$$RESTAI_UV run --no-group gpu uvicorn restai.main:app --host $${RESTAI_HOST:-127.0.0.1} --port $${RESTAI_PORT:-9000} --workers $${RESTAI_WORKERS:-4}" >> /tmp/restai.service; \
	echo "Restart=always" >> /tmp/restai.service; \
	echo "RestartSec=5" >> /tmp/restai.service; \
	echo "" >> /tmp/restai.service; \
	echo "[Install]" >> /tmp/restai.service; \
	echo "WantedBy=multi-user.target" >> /tmp/restai.service; \
	sudo cp /tmp/restai.service /etc/systemd/system/restai.service; \
	rm /tmp/restai.service; \
	sudo systemctl daemon-reload; \
	sudo systemctl enable restai; \
	sudo systemctl start restai; \
	echo ""; \
	echo "RESTai systemd service installed and started."; \
	echo "  Status:  sudo systemctl status restai"; \
	echo "  Logs:    sudo journalctl -u restai -f"; \
	echo "  Stop:    sudo systemctl stop restai"; \
	echo "  Restart: sudo systemctl restart restai"

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

.PHONY: cron
cron:
	@RESTAI_DIR=$$(pwd); \
	CURRENT=$$(crontab -l 2>/dev/null || true); \
	NEW="$$CURRENT"; \
	if ! echo "$$CURRENT" | grep -q "restai-sync"; then \
	  NEW="$$NEW"$$'\n'"*/5 * * * * cd $$RESTAI_DIR && uv run --no-group gpu python scripts/sync.py >> /var/log/restai-sync.log 2>&1 # restai-sync"; \
	  echo "Added: restai-sync"; \
	else echo "Already installed: restai-sync"; fi; \
	if ! echo "$$CURRENT" | grep -q "restai-telegram"; then \
	  NEW="$$NEW"$$'\n'"*/1 * * * * cd $$RESTAI_DIR && uv run --no-group gpu python scripts/telegram.py >> /var/log/restai-telegram.log 2>&1 # restai-telegram"; \
	  echo "Added: restai-telegram"; \
	else echo "Already installed: restai-telegram"; fi; \
	if ! echo "$$CURRENT" | grep -q "restai-docker-cleanup"; then \
	  NEW="$$NEW"$$'\n'"* * * * * cd $$RESTAI_DIR && uv run --no-group gpu python scripts/docker_cleanup.py >> /var/log/restai-docker-cleanup.log 2>&1 # restai-docker-cleanup"; \
	  echo "Added: restai-docker-cleanup"; \
	else echo "Already installed: restai-docker-cleanup"; fi; \
	echo "$$NEW" | crontab -
	@echo "Cron jobs installed:"
	@crontab -l | grep restai || true

.PHONY: cron-remove
cron-remove:
	@( crontab -l 2>/dev/null | grep -v "restai-sync\|restai-telegram\|restai-docker-cleanup" ) | crontab -
	@echo "RESTai cron jobs removed."

.PHONY: sync
sync:
	uv run --no-group gpu python scripts/sync.py

.PHONY: telegram
telegram:
	uv run --no-group gpu python scripts/telegram.py

.PHONY: slack
slack:
	uv run --no-group gpu python scripts/slack.py

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

.PHONY: version
version:
	@CURRENT=$$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/'); \
	MAJOR=$$(echo $$CURRENT | cut -d. -f1); \
	MINOR=$$(echo $$CURRENT | cut -d. -f2); \
	PATCH=$$(echo $$CURRENT | cut -d. -f3); \
	NEW_PATCH=$$((PATCH + 1)); \
	NEW_VERSION="$$MAJOR.$$MINOR.$$NEW_PATCH"; \
	echo "Bumping version: $$CURRENT → $$NEW_VERSION"; \
	sed -i "s/^version = \"$$CURRENT\"/version = \"$$NEW_VERSION\"/" pyproject.toml; \
	echo "Syncing lock file..."; \
	uv sync --no-group gpu; \
	echo "Committing..."; \
	git add pyproject.toml uv.lock; \
	git commit -m "v$$NEW_VERSION"; \
	echo "Tagging v$$NEW_VERSION..."; \
	git tag "v$$NEW_VERSION"; \
	echo "Pushing..."; \
	git push && git push --tags; \
	echo "Creating GitHub release..."; \
	gh release create "v$$NEW_VERSION" --title "v$$NEW_VERSION" --generate-notes; \
	echo "Done: v$$NEW_VERSION released."

.PHONY: test
test:
	pytest tests

.PHONY: code
code:
	black app/*.py

.PHONY: clean
clean:
	rm -rf frontend/build/*

.PHONY: dockershell
dockershell:
	@docker run --rm -t -i -v $(shell pwd):/app restai bash

.PHONY: dockerbuild
dockerbuild:
	@docker build -t restai .

