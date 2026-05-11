.PHONY: install test lint replay reflect stream clean

install:
	python -m pip install -e ".[dev,ml,ui]"

test:
	pytest -q

lint:
	ruff check .

replay:
	python -m replay

reflect:
	python -m reflector

stream:
	python -m orchestrator

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__
