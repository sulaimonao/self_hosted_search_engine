.PHONY: setup crawl index reindex serve test lint format clean

VENV?=.venv
PYTHON?=python3
PIP?=$(VENV)/bin/pip

setup: ## create venv & install deps
@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
$(PIP) install --upgrade pip
$(PIP) install -r requirements.txt
$(VENV)/bin/python -m playwright install --with-deps chromium || true

crawl: ## run crawler with config
$(VENV)/bin/python scripts/manage.py crawl

index: ## incremental index
$(VENV)/bin/python scripts/manage.py index update

reindex: ## full rebuild
$(VENV)/bin/python scripts/manage.py index full

serve: ## run Flask UI
$(VENV)/bin/python scripts/manage.py serve

stats: ## show latest crawl stats
$(VENV)/bin/python scripts/manage.py stats

test: ## run pytest
$(VENV)/bin/pytest -q

lint: ## placeholder for linter hook
@echo "No linters configured"

clean:
rm -rf $(VENV)
rm -rf data index __pycache__ */__pycache__
