.PHONY: check format lint test file-lines api-format api-lint api-typecheck api-test web-format web-lint web-check web-test

check: file-lines api-lint api-typecheck api-test web-lint web-check web-test

format: api-format web-format

lint: file-lines api-lint web-lint

test: api-test web-test

file-lines:
	python3 scripts/check_file_lengths.py

api-format:
	cd api && python -m ruff format .
	cd api && python -m ruff check --fix .

api-lint:
	cd api && python -m ruff check .
	cd api && python -m ruff format --check .

api-typecheck:
	cd api && python -m pyright

api-test:
	cd api && python -m pytest

web-format:
	cd web && npm run format

web-lint:
	cd web && npm run lint

web-check:
	cd web && npm run check

web-test:
	cd web && npm run test
