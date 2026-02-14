PYTHON ?= python3
VENV_DIR ?= .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
DEV_STAMP := $(VENV_DIR)/.dev-deps.stamp

.PHONY: setup-dev check-dev test test-unit test-contract

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV_DIR)

$(DEV_STAMP): pyproject.toml requirements.txt | $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install --no-build-isolation -e ".[dev]"
	touch $(DEV_STAMP)

setup-dev: $(DEV_STAMP)

check-dev:
	@test -x "$(VENV_PYTHON)" || (echo "Missing $(VENV_PYTHON). Run 'make setup-dev'." && exit 1)
	@test -f "$(DEV_STAMP)" || (echo "Missing dev dependency stamp. Run 'make setup-dev'." && exit 1)
	@$(VENV_PYTHON) -c "import pytest" >/dev/null 2>&1 || (echo "pytest is not installed in $(VENV_DIR). Run 'make setup-dev'." && exit 1)

test: check-dev
	$(VENV_PYTHON) -m pytest -v

test-unit: check-dev
	$(VENV_PYTHON) -m pytest -m "not contract" -v

test-contract: check-dev
	$(VENV_PYTHON) -m pytest -m contract -v
