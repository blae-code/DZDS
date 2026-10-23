VENV ?= .venv
PY := $(VENV)/bin/python
SHELL := /bin/bash
ENV := set -a; [ -f .env ] && source .env; set +a;

.PHONY: setup pull push logs validate modstring panel-mods panel-copy keys calibrate test gm

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

panel-mods:
	$(PY) tools/modstring.py panel --write

# Put the Additional Mods line on the clipboard (Wayland).
panel-copy: panel-mods
	wl-copy -n < config/panel_additional_mods.txt

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
	-$(ENV) $(PY) tools/maps_check.py

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

.PHONY: arrivals
arrivals:       # presets/arrivals.yaml + map arrival_sites -> profiles/DZDS/arrivals.json (init.c)
	$(ENV) $(PY) tools/arrivals.py

.PHONY: kan-camps
kan-camps:      # presets/kan_camps.yaml -> KAN camps.json role counts (server STOPPED)
	$(ENV) $(PY) tools/kan_camps.py

.PHONY: economy
economy:
	$(ENV) $(PY) tools/economy.py

.PHONY: patrols diplomacy prepare-restart
patrols:
	$(ENV) $(PY) tools/patrol_gen.py $(if $(INTERIM),--interim)

diplomacy:
	$(ENV) $(PY) tools/diplomacy.py

# Everything that should run between restarts, in order, before `make push`.
prepare-restart: war-turn economy diplomacy patrols zone-events vehicle-events front-plan loadouts dzds-profile arrivals overlays calibrate validate
	@echo "Ready: review git diff, then 'make push' and restart from the GSP panel."

.PHONY: war-status war-turn
war-status:
	$(ENV) $(PY) tools/war.py status

war-turn:
	$(ENV) $(PY) tools/war.py turn

.PHONY: front-plan
front-plan:
	$(ENV) $(PY) tools/front_plan.py

.PHONY: loadouts loadouts-check
loadouts:
	$(ENV) $(PY) tools/loadouts.py build

loadouts-check:
	set -a; [ -f .env ] && source .env; set +a; $(PY) tools/loadouts.py check

.PHONY: dzds-profile
dzds-profile:
	$(ENV) $(PY) tools/dzds_profile.py

.PHONY: vehicle-events
vehicle-events:
	set -a; [ -f .env ] && source .env; set +a; $(PY) tools/vehicle_events.py

.PHONY: mod-drift
mod-drift:
	set -a; [ -f .env ] && source .env; set +a; $(PY) tools/mod_drift.py $(if $(ALL),--all)

.PHONY: reset-respawns
reset-respawns:   # server STOPPED: clear arrivals cooldowns + reset characters (DRY_RUN=1, YES=1, PLAYER=blae); LIVE=1 PLAYER=..: running server, cooldowns only
	$(ENV) $(PY) tools/reset_respawns.py $(if $(DRY_RUN),--dry-run) $(if $(YES),--yes) $(if $(PLAYER),--player "$(PLAYER)") $(if $(LIVE),--live)

.PHONY: specs
specs:
	$(PY) tools/specs.py

.PHONY: survey
survey:         # candidate sites per role from the active mission's mapgrouppos.xml
	$(ENV) $(PY) tools/map_survey.py

.PHONY: zone-events
zone-events:    # event mods act only inside zones (presets/zone_events.yaml)
	$(ENV) $(PY) tools/zone_events.py

.PHONY: encounter-audit
encounter-audit: # AI encounters outside zones per player-session (target <= 1 per 3)
	$(ENV) $(PY) tools/encounter_audit.py
