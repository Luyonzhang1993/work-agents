PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: dev install

dev:
	$(PYTHON) -m app

install:
	$(PIP) install -e .
