VENV ?= .venv
PY := $(VENV)/bin/python
SHELL := /bin/bash

.PHONY: setup pull push logs validate modstring keys calibrate test gm

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e '.[dev]'
	@[ -f .env ] || { cp .env.example .env; echo "Created .env, fill in credentials"; }

pull:
	scripts/sync.sh pull

push:
	scripts/sync.sh push

logs:
	scripts/sync.sh logs

validate:
	scripts/validate.sh

modstring:
	$(PY) tools/modstring.py string -v

keys:
	set -a; [ -f .env ] && source .env; set +a; $(PY) tools/modstring.py keys

calibrate:
	$(PY) tools/apply_ai_calibration.py

test:
	$(PY) -m pytest -q

gm:
	$(PY) -m gamemaster.gm_orchestrator
