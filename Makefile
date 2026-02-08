.PHONY: help install dev test test-cov lint format run clean db-reset check pot-start pot-stop pot-logs pot-status prereqs setup

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help:  ## Show this help message
	@echo "$(BLUE)Discord Music Player - Available Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Quick Start:$(NC)"
	@echo "  1. make setup        - Full first-time setup"
	@echo "  2. Edit .env with your Discord token"
	@echo "  3. make run          - Start the bot"

prereqs:  ## Check that required system tools are installed
	@echo "$(BLUE)Checking prerequisites...$(NC)"
	@FAIL=0; \
	PYTHON_VERSION=$$(python3 --version 2>/dev/null | grep -oP '\d+\.\d+'); \
	if [ -z "$$PYTHON_VERSION" ]; then \
		echo "  $(YELLOW)✗ python3       not found$(NC)  — install Python 3.12+ from https://python.org"; \
		FAIL=1; \
	else \
		MAJOR=$$(echo "$$PYTHON_VERSION" | cut -d. -f1); \
		MINOR=$$(echo "$$PYTHON_VERSION" | cut -d. -f2); \
		if [ "$$MAJOR" -lt 3 ] || ([ "$$MAJOR" -eq 3 ] && [ "$$MINOR" -lt 12 ]); then \
			echo "  $(YELLOW)✗ python3       $$PYTHON_VERSION (need 3.12+)$(NC)"; \
			FAIL=1; \
		else \
			echo "  $(GREEN)✓ python3       $$PYTHON_VERSION$(NC)"; \
		fi; \
	fi; \
	if command -v ffmpeg >/dev/null 2>&1; then \
		echo "  $(GREEN)✓ ffmpeg        $$(ffmpeg -version 2>&1 | head -1 | grep -oP 'version \S+')$(NC)"; \
	else \
		echo "  $(YELLOW)✗ ffmpeg        not found$(NC)  — install from https://ffmpeg.org"; \
		FAIL=1; \
	fi; \
	if command -v docker >/dev/null 2>&1; then \
		echo "  $(GREEN)✓ docker        $$(docker --version 2>&1 | grep -oP '\d+\.\d+\.\d+')$(NC)"; \
	else \
		echo "  $(YELLOW)✗ docker        not found$(NC)  — install from https://docs.docker.com/get-docker/"; \
		FAIL=1; \
	fi; \
	if command -v docker-compose >/dev/null 2>&1 || docker compose version >/dev/null 2>&1; then \
		echo "  $(GREEN)✓ docker-compose$(NC)"; \
	else \
		echo "  $(YELLOW)✗ docker-compose not found$(NC)  — install Docker Compose"; \
		FAIL=1; \
	fi; \
	if command -v tmux >/dev/null 2>&1; then \
		echo "  $(GREEN)✓ tmux          $$(tmux -V 2>&1 | grep -oP '[\d.]+')$(NC)"; \
	else \
		echo "  $(YELLOW)  tmux          not found (optional, needed for make run-tmux)$(NC)"; \
	fi; \
	echo ""; \
	if [ $$FAIL -ne 0 ]; then \
		echo "$(YELLOW)Some prerequisites are missing. Install them and re-run make prereqs.$(NC)"; \
		exit 1; \
	fi; \
	echo "$(BLUE)System libraries (needed if PyNaCl wheel is unavailable):$(NC)"; \
	if command -v dpkg >/dev/null 2>&1; then \
		for pkg in libffi-dev libsodium-dev python3-dev; do \
			if dpkg -s $$pkg >/dev/null 2>&1; then \
				echo "  $(GREEN)✓ $$pkg$(NC)"; \
			else \
				echo "  $(YELLOW)  $$pkg          not installed (apt install $$pkg)$(NC)"; \
			fi; \
		done; \
	elif command -v brew >/dev/null 2>&1; then \
		for pkg in libffi libsodium; do \
			if brew list $$pkg >/dev/null 2>&1; then \
				echo "  $(GREEN)✓ $$pkg$(NC)"; \
			else \
				echo "  $(YELLOW)  $$pkg          not installed (brew install $$pkg)$(NC)"; \
			fi; \
		done; \
	else \
		echo "  $(YELLOW)  Could not detect package manager. Ensure libffi and libsodium are installed.$(NC)"; \
	fi
	@echo ""
	@echo "$(GREEN)✓ All prerequisites met$(NC)"

setup: prereqs  ## Full first-time setup (prereqs → venv → install → .env → POT)
	@echo ""
	@echo "$(BLUE)Running full setup...$(NC)"
	@if [ -z "$$VIRTUAL_ENV" ] && [ ! -d .venv ]; then \
		echo "$(BLUE)Creating virtual environment in .venv/...$(NC)"; \
		python3 -m venv .venv; \
		echo "$(GREEN)✓ Virtual environment created$(NC)"; \
	elif [ -n "$$VIRTUAL_ENV" ]; then \
		echo "$(GREEN)✓ Already in a virtual environment$(NC)"; \
	else \
		echo "$(GREEN)✓ .venv/ already exists$(NC)"; \
	fi
	@echo "$(BLUE)Installing dependencies...$(NC)"
	@if [ -n "$$VIRTUAL_ENV" ]; then \
		pip install -e .; \
	else \
		.venv/bin/pip install -e .; \
	fi
	@echo "$(GREEN)✓ Dependencies installed$(NC)"
	@$(MAKE) setup-env
	@$(MAKE) pot-start
	@echo ""
	@echo "$(GREEN)========================================$(NC)"
	@echo "$(GREEN)  Setup complete!$(NC)"
	@echo "$(GREEN)========================================$(NC)"
	@echo ""
	@echo "$(YELLOW)Next steps:$(NC)"
	@if [ -z "$$VIRTUAL_ENV" ] && [ -d .venv ]; then \
		echo "  1. source .venv/bin/activate"; \
		echo "  2. Edit .env with your Discord token"; \
		echo "  3. make run"; \
	else \
		echo "  1. Edit .env with your Discord token"; \
		echo "  2. make run"; \
	fi

install:  ## Install production dependencies
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	pip install -e .
	@echo "$(GREEN)✓ Installation complete$(NC)"

dev:  ## Install development dependencies
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	pip install -e ".[dev,test]"
	@echo "$(GREEN)✓ Development environment ready$(NC)"

test:  ## Run tests
	@echo "$(BLUE)Running tests...$(NC)"
	pytest

test-cov:  ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	pytest --cov=src --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/index.html$(NC)"

lint:  ## Run linting checks
	@echo "$(BLUE)Running linting checks...$(NC)"
	ruff check .
	@echo "$(GREEN)✓ Linting complete$(NC)"

format:  ## Format code with ruff
	@echo "$(BLUE)Formatting code...$(NC)"
	ruff format .
	ruff check --fix .
	@echo "$(GREEN)✓ Code formatted$(NC)"

check:  ## Run all checks (lint + test)
	@echo "$(BLUE)Running all checks...$(NC)"
	@$(MAKE) lint
	@$(MAKE) test
	@echo "$(GREEN)✓ All checks passed$(NC)"

run:  ## Run the Discord bot
	@echo "$(BLUE)Starting Discord Music Player...$(NC)"
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)Warning: .env file not found. Copy .env.example and configure it first.$(NC)"; \
		exit 1; \
	fi
	python -m discord_music_player

run-tmux:  ## Run the bot in tmux with auto-respawn
	@echo "$(BLUE)Starting bot in tmux session...$(NC)"
	./music_start.py start --respawn

db-reset:  ## Reset the database (WARNING: deletes all data)
	@echo "$(YELLOW)⚠ This will delete all database data!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		rm -f data/bot.db data/bot.db-shm data/bot.db-wal; \
		echo "$(GREEN)✓ Database reset$(NC)"; \
	else \
		echo "Cancelled"; \
	fi

clean:  ## Clean up temporary files and caches
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf htmlcov .coverage 2>/dev/null || true
	rm -rf build dist 2>/dev/null || true
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

setup-env:  ## Create .env file from example
	@if [ -f .env ]; then \
		echo "$(YELLOW).env file already exists. Skipping...$(NC)"; \
	else \
		cp .env.example .env; \
		echo "$(GREEN)✓ Created .env file. Please edit it with your configuration.$(NC)"; \
	fi

info:  ## Show project information
	@echo "$(BLUE)Project Information$(NC)"
	@echo "  Name: Discord Music Player Bot"
	@echo "  Python: $$(python --version 2>&1)"
	@echo "  pip: $$(pip --version 2>&1 | cut -d' ' -f1-2)"
	@echo ""
	@echo "$(BLUE)Dependencies Status$(NC)"
	@pip show discord.py yt-dlp pydantic aiosqlite 2>/dev/null | grep -E "^(Name|Version):" || echo "  Run 'make install' first"

pot-start:  ## Start the POT provider container
	@echo "$(BLUE)Starting POT provider container...$(NC)"
	@docker-compose up -d bgutil-provider
	@sleep 2
	@$(MAKE) pot-status

pot-stop:  ## Stop the POT provider container
	@echo "$(BLUE)Stopping POT provider container...$(NC)"
	@docker-compose stop bgutil-provider
	@echo "$(GREEN)✓ POT provider stopped$(NC)"

pot-logs:  ## Show POT provider logs
	@docker logs bgutil-provider --tail 50 --follow

pot-status:  ## Check POT provider status
	@echo "$(BLUE)POT Provider Status$(NC)"
	@if docker ps | grep -q bgutil-provider; then \
		echo "  Status: $(GREEN)Running$(NC)"; \
		echo "  URL: http://127.0.0.1:4416"; \
		echo ""; \
		docker logs bgutil-provider --tail 5 | grep -E "(poToken:|Started POT server)" || true; \
	else \
		echo "  Status: $(YELLOW)Not running$(NC)"; \
		echo "  Run 'make pot-start' to start it"; \
	fi
