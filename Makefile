PYTHON := .venv/bin/python
PIP := .venv/bin/pip
NPM := npm

.PHONY: dev install dev-frontend dev-full

dev:
	$(PYTHON) -m app

install:
	$(PIP) install -e .

install-frontend:
	cd frontend && $(NPM) install

dev-frontend:
	cd frontend && $(NPM) run dev

dev-full:
	$(MAKE) -j2 dev dev-frontend
