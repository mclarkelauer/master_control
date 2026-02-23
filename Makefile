.PHONY: install start stop restart status logs test lint validate clean help \
       setup setup-local deploy deploy-client deploy-dry-run deploy-sync \
       build-image

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies and set up project
	@bash scripts/install.sh

start: ## Start the control daemon in the background
	@bash scripts/mctl-daemon.sh start

stop: ## Stop the running control daemon
	@bash scripts/mctl-daemon.sh stop

restart: ## Restart the control daemon
	@bash scripts/mctl-daemon.sh restart

status: ## Check daemon status and list workloads
	@bash scripts/mctl-daemon.sh status

logs: ## Show last 50 lines of daemon log
	@bash scripts/mctl-daemon.sh logs

test: ## Run all tests
	uv run pytest -v

lint: ## Run linter
	uv run ruff check src/ tests/ agents/

validate: ## Validate workload config files
	uv run master-control --config-dir configs validate

clean: ## Remove runtime artifacts (logs, db, pid, socket)
	rm -rf logs/ run/ master_control.db /tmp/master_control.sock
	@echo "Cleaned runtime artifacts"

# --- Deployment ---

setup: ## Set up control host and deploy to clients
	@bash scripts/setup-control-host.sh

setup-local: ## Set up control host only (no client deployment)
	@bash scripts/setup-control-host.sh --local-only

deploy: ## Deploy to all clients in inventory
	@bash scripts/deploy-clients.sh

deploy-client: ## Deploy to a specific client: make deploy-client CLIENT=name
	@bash scripts/deploy-clients.sh --client $(CLIENT)

deploy-dry-run: ## Show what deployment would do without doing it
	@bash scripts/deploy-clients.sh --dry-run

deploy-sync: ## Sync files and configs to clients without restarting
	@bash scripts/deploy-clients.sh --sync-only

# --- SD Card Imaging ---

build-image: ## Build a pre-baked Pi image: make build-image IMAGE=raspios.img.xz HOSTNAME=node-1
	@sudo bash scripts/build-image.sh --image $(IMAGE) --hostname $(HOSTNAME) $(EXTRA_ARGS)
