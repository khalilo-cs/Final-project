SERVICES := auth-service project-service code-analyzer db-analyzer report-analyzer viva-engine fraud-detector sandbox-runner report-generator speech-service
VENV ?= .venv
PY := $(abspath $(VENV))/bin/python

.PHONY: install lint format test up down web migration

install:
	python3 -m venv $(VENV)
	$(PY) -m pip install -q ruff $(foreach s,$(SERVICES),-r services/$(s)/requirements-dev.txt)

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .

test:
	@set -e; for s in $(SERVICES); do echo "== $$s"; (cd services/$$s && $(PY) -m pytest -q); done
	@echo "== tools/evaluation"; $(PY) -m pytest -q tools/evaluation/tests

up:
	docker compose up --build

down:
	docker compose down

web:
	cd frontend && npm install && npx vite

# New schema change: make migration SVC=project-service MSG="add x column"
migration:
	cd services/$(SVC) && $(PY) -m alembic revision --autogenerate -m "$(MSG)"
