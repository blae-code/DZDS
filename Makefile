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
	set -a; [ -f .env ] && source .env; set +a; $(PY) tools/apply_ai_calibration.py

test:
	$(PY) -m pytest -q

gm:
	$(PY) -m gamemaster.gm_orchestrator

# ---- Pre-purchase / offline ----
.PHONY: verify-mods find-mod maps-check types mod-types fake-rcon sim gm-sim gm-probe

verify-mods:
	$(PY) tools/verify_mods.py

find-mod:
	$(PY) tools/find_mod.py "$(Q)"

maps-check:
	-$(PY) tools/maps_check.py

types:
	$(PY) tools/types_gen.py

mod-types:
	set -a; [ -f .env ] && source .env; set +a; $(PY) tools/collect_mod_types.py

fake-rcon:
	$(PY) tools/fake_rcon.py --password changeme

sim:
	$(PY) tools/adm_simulator.py

gm-sim:
	GM_TELEMETRY=file GM_ADM_FILE=gm_state/sim.ADM GM_DRY_RUN=0 RCON_HOST=127.0.0.1 \
	RCON_PORT=2310 RCON_PASSWORD=changeme $(PY) -m gamemaster.gm_orchestrator

gm-probe:
	$(PY) tools/gm_probe.py

.PHONY: overlays
overlays:
	set -a; [ -f .env ] && source .env; set +a; $(PY) tools/apply_overlays.py

.PHONY: economy
economy:
	set -a; [ -f .env ] && source .env; set +a; $(PY) tools/economy.py $(if $(PHASE),--phase $(PHASE))

.PHONY: patrols diplomacy prepare-restart
patrols:
	$(PY) tools/patrol_gen.py $(if $(INTERIM),--interim)

diplomacy:
	$(PY) tools/diplomacy.py

# Everything that should run between restarts, in order, before `make push`.
prepare-restart: economy diplomacy patrols overlays calibrate validate
	@echo "Ready: review git diff, then 'make push' and restart from the GSP panel."
