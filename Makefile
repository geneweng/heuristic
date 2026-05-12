.PHONY: install test lint replay reflect reflect-fixture stream fixture results clean

PYTHON ?= python3
PYTHONPATH := .:skills/common:skills/fraud-ml:skills/fraud-rules:skills/fraud-replay:skills/fraud-reflector:skills/orchestrator:results
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

reflect-fixture:
	$(PYTHON) data/reflect/build_fixture.py

reflect: reflect-fixture
	$(PYTHON) -m reflector

results:
	$(PYTHON) -m simulate

stream:
	$(PYTHON) -m orchestrator

clean:
	rm -rf .pytest_cache .ruff_cache results/replay_report.* **/__pycache__
