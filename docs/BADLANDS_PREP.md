# Badlands (Nasdara) Release Runbook

**Release:** Bohemia's Steam announcement says **15 October 2026** (check the exact hour in
your timezone, which may be the 14th). Ships with **game update 1.30**. Nasdara Province is
267 km², larger than Chernarus (225 km²), and arid with scarce water.

## Before release (now)
- [ ] Keep all Chernarus content role-based (`maps/_roles.yaml`), not tied to town names.
- [ ] Decide whether `coastal_town` applies to Nasdara; adjust role minimums if not.
- [ ] Note which mods are critical vs. optional, so you know what can be disabled on day one.

## Release day
1. **Expect mod breakage.** 1.30 is a game update; script mods (CF, Expansion, Zen, VPP)
   usually need patches. Run `make verify-mods` daily: an `updated` date after release
   is a good sign the author has patched.
2. Update the local test server: `scripts/local_server.sh install` (re-runs `app_update`).
3. Find the new mission folder name in `<server>/mpmissions/` → `maps/nasdara.yaml: mission`.
4. Map extents → `bounds`. Find the world size in the mission/map config or on iZurvive once
   Nasdara is added. 267 km² suggests ~16.3 km per side, but verify; don't assume square.
5. Named locations: fly around with VPPAdminTools (or use iZurvive) and record `[x, z]` for
   each town, base and airfield in `locations:`; assign them to `roles:`.
6. `make maps-check` until Nasdara shows OK.
7. Point the GM at it: `GM_MAP=nasdara`.
8. Faction territories in `presets/factions.yaml` use roles, so they port automatically.
   Re-check `types_dzds.yaml` usage zones against Nasdara's mapgroupproto.
9. Expansion AI patrol/waypoint files are map-specific. Regenerate on the local server, then
   rebuild from the role-based locations.

## Not before
Don't switch your live (GSP) server to Nasdara until CF, Expansion-Core/AI and VPP have 1.30
updates and the Phase 4 checklist passes on the local server.
