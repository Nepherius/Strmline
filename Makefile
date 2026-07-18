.PHONY: check format lint test api-format api-lint api-typecheck api-test web-format web-lint web-check web-test

API_PYTHON ?= .venv/bin/python

check: api-lint api-typecheck api-test web-lint web-check web-test

format: api-format web-format

lint: api-lint web-lint

test: api-test web-test

api-format:
	cd api && $(API_PYTHON) -m ruff format .
	cd api && $(API_PYTHON) -m ruff check --fix .

api-lint:
	cd api && $(API_PYTHON) -m ruff check .
	cd api && $(API_PYTHON) -m ruff format --check .

api-typecheck:
	cd api && $(API_PYTHON) -m pyright

api-test:
	cd api && $(API_PYTHON) -m pytest

web-format:
	cd web && npm run format

web-lint:
	cd web && npm run lint

web-check:
	cd web && npm run check

web-test:
	cd web && npm run test
