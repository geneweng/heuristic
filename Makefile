.PHONY: install test lint replay reflect stream fixture clean

PYTHON ?= python3
PYTHONPATH := skills/common:skills/fraud-ml:skills/fraud-rules:skills/fraud-replay:skills/fraud-reflector:skills/orchestrator
export PYTHONPATH

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .

fixture:
	$(PYTHON) data/replay/build_fixture.py

replay: fixture
	$(PYTHON) -m replay

reflect:
	$(PYTHON) -m reflector

stream:
	$(PYTHON) -m orchestrator

clean:
	rm -rf .pytest_cache .ruff_cache results/replay_report.* **/__pycache__
