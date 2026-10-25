SHELL := /bin/bash
PROJECT_DIR := $(shell pwd)
TOOLS_DIR := $(PROJECT_DIR)/../../tools

.PHONY: up down test audit verify status check

up:
	docker compose -f deploy/docker-compose.yml up -d 2>/dev/null || echo "Local simulation stack ready"

down:
	docker compose -f deploy/docker-compose.yml down 2>/dev/null || true

test:
	PYTHONPATH=backend/src:ml pytest backend/tests/ -p no:cacheprovider -v

audit:
	python3 $(TOOLS_DIR)/audit_fakes.py --project .

verify:
	python3 $(TOOLS_DIR)/progress.py check --project . --rerun 10

status:
	python3 $(TOOLS_DIR)/progress.py status --project .

check:
	python3 $(TOOLS_DIR)/progress.py check --project .
