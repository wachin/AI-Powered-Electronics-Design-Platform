# One entry point for the commands a contributor or an agent needs.
#
# Every target runs the venv's Python, never the system one: `pcbnew` lives in
# the system interpreter, everything else in the venv, and mixing them is the
# most common way to get a confusing import error here.
#
#   make            # this help
#   make test       # the suite, without the catalog
#
# `make test-catalog` needs the catalog path. Pass it in, or export it:
#   make test-catalog CATALOG=/path/to/jlcparts.sqlite3
#   export JLC_PARTS_CATALOG=/path/to/jlcparts.sqlite3 && make test-catalog

PY      ?= venv/bin/python
PIP     ?= venv/bin/pip
CLI     ?= venv/bin/ai-electronics-design
CATALOG ?= $(JLC_PARTS_CATALOG)
OUTPUT  ?= output_design/demo
F       ?= tests

.DEFAULT_GOAL := help
.PHONY: help check-venv install test test-catalog test-file lint compile-check diagnose demo catalog clean frontend

# Every target below needs the venv. A fresh clone does not have one yet, and
# "make test" there used to fail with "venv/bin/python: No such file or
# directory", which tells a newcomer nothing about what to do next.
check-venv:
	@test -x "$(PY)" || { \
		echo "There is no virtualenv at $(PY)."; \
		echo "Create it first:   make install"; \
		echo "Or by hand:        python3 -m venv venv && venv/bin/pip install -e \"[dev]\""; \
		echo "Details:           docs/development.md"; \
		exit 1; }

help: ## Show this help
	@echo "Targets:"
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-16s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "ENV: venv/bin/python, JLC_PARTS_CATALOG, DSH_KICAD_CLI"

install: ## Create the venv and install in editable mode (with dev tools)
	python3 -m venv venv
	$(PIP) install -e ".[dev]"

test: check-venv ## Run the full suite without the component catalog
	$(PY) -m pytest tests/ -q

test-catalog: check-venv ## Run the full suite against the real catalog (needs CATALOG)
	@test -n "$(CATALOG)" || { \
		echo "Set the catalog path: make test-catalog CATALOG=/path/to/jlcparts.sqlite3"; \
		echo "Without it these tests skip, which is why 'make test' passes without them."; \
		exit 1; }
	JLC_PARTS_CATALOG=$(CATALOG) $(PY) -m pytest tests/ -q

test-file: check-venv ## Run one file or directory: make test-file F=tests/test_erc.py
	$(PY) -m pytest $(F) -q

lint: check-venv ## Ruff: undefined names, unused imports, shadowed definitions, duplicated keys
	@$(PY) -m ruff --version >/dev/null 2>&1 || { \
		echo "ruff is not installed: $(PIP) install ruff"; exit 1; }
	$(PY) -m ruff check src/ tests/

compile-check: check-venv ## Byte-compile everything, as CI does
	$(PY) -m compileall -q src main.py && echo "compile-check ok"

diagnose: check-venv ## Report which external tools are installed
	$(CLI) --diagnose

demo: check-venv ## Build a demonstration design into OUTPUT
	$(CLI) -p "5V to 3.3V LDO with an LED indicator" -o $(OUTPUT) --no-spice --no-routing
	@echo "Wrote $(OUTPUT)"

catalog: check-venv ## Download the component catalog (146 MB, one time)
	$(CLI) catalog-setup

frontend: ## Build the web frontend
	cd frontend && npm ci && npm run build

clean: ## Remove generated output and caches
	rm -rf output_design .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "cleaned"
