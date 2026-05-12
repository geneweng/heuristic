.PHONY: install test lint replay reflect reflect-fixture stream fixture results ui data ml-train clean

PYTHON ?= python3
PYTHONPATH := .:skills/common:skills/fraud-ml:skills/fraud-rules:skills/fraud-replay:skills/fraud-reflector:skills/orchestrator:skills/analyst-ui:results
export PYTHONPATH

install:
	$(PYTHON) -m pip install -e ".[dev]"

data:
	$(PYTHON) data/build_splits.py

ml-train:
	$(PYTHON) skills/fraud-ml/train.py

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

ui:
	$(PYTHON) -m streamlit run skills/analyst-ui/app.py

stream:
	$(PYTHON) -m orchestrator

clean:
	rm -rf .pytest_cache .ruff_cache results/replay_report.* **/__pycache__
