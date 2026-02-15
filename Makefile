PYTHON ?= python3
VENV_DIR ?= .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
DEV_STAMP := $(VENV_DIR)/.dev-deps.stamp

.PHONY: setup-dev check-dev test test-unit test-contract test-integration test-integration-discord test-integration-rcon typecheck

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

test-integration: test-integration-discord test-integration-rcon

test-integration-discord: check-dev
	$(VENV_PYTHON) -m pytest -v tests/test_discord_integration.py tests/test_plugin_chat_bridge.py tests/test_plugin_admin_request.py

test-integration-rcon: check-dev
	$(VENV_PYTHON) -m pytest -v tests/test_rcon_client.py tests/test_rcon_helpers.py tests/test_rcon_protocol.py tests/test_server.py

typecheck: check-dev
	@$(VENV_PYTHON) -m pyright --version >/dev/null 2>&1 || (echo "pyright is not installed in $(VENV_DIR). Run 'make setup-dev' in a network-enabled environment." && exit 1)
	$(VENV_PYTHON) -m pyright --pythonpath $(VENV_PYTHON)
