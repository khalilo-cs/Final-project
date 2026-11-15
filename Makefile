SERVICES := auth-service project-service code-analyzer db-analyzer report-analyzer viva-engine fraud-detector sandbox-runner
VENV ?= .venv
PY := $(abspath $(VENV))/bin/python

.PHONY: install lint format test up down web

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

up:
	docker compose up --build

down:
	docker compose down

web:
	cd frontend && npm install && npx vite
