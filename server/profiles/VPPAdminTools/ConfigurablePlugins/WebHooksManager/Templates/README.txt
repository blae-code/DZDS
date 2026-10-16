VPP Admin Tools webhook templates
=================================

Each webhook has a folder named after its id with one <event>.tpl per event: the request body sent for it.
Edit them here or in the WebHooks menu; the server reads them at start (or on Reload in the menu).
Delete a file to get the webhook's preset template back.

Syntax:
  {{victim.name}}                        a variable (JSON-escaped for JSON webhooks)
  {{victim.id|steamurl}}                 filters: upper lower trim truncate:N default:TEXT round:N number steamurl raw json
  {{#if killer.id}} ... {{else}} ... {{/if}}   shown when the variable is not empty
  {{#unless killer.id}} ... {{/unless}}       shown when it is empty
  {{#ifeq cause suicide}} ... {{/ifeq}}       shown when it equals the value
  {{! comment }}
  {{hook.<name>}}                        a custom variable of the webhook (username, avatar, chat_id, ...)

Webhooks:

Events and their variables:

  admin.action
    {{admin.name}}  e.g. SurvivorAdmin
    {{admin.id}}  e.g. 76561198000000000
    {{action}}  e.g. [ItemManager] Spawned Item: M4A1 on self
    {{action.text}}  e.g. Spawned Item: M4A1 on self
    {{module}}  e.g. ItemManager
    {{event}}  e.g. admin.action
    {{server.name}}  e.g. My DayZ Server
    {{server.ip}}  e.g. 203.0.113.10
    {{server.port}}  e.g. 27016
    {{server.map}}  e.g. chernarusplus
    {{players}}  e.g. 12
    {{time.iso}}  e.g. 2026-09-29T18:04:00.000Z
    {{time.unix}}  e.g. 1790705040
    {{time.date}}  e.g. 2026-09-29
    {{time.time}}  e.g. 18:04:00

  kill
    {{victim.name}}  e.g. Survivor
    {{victim.id}}  e.g. 76561198000000001
    {{victim.pos}}  e.g. 7500.1, 290.5, 7700.2
    {{killer.name}}  e.g. Bandit
    {{killer.id}}  e.g. 76561198000000002
    {{killer.pos}}  e.g. 7560.3, 291.0, 7712.8
    {{cause}}  e.g. player
    {{weapon}}  e.g. M4-A1
    {{distance}}  e.g. 61.4
    {{details}}  e.g. Survivor (7500, 7700) killed by: Bandit (7560, 7712) with [M4-A1] from [61.4] meters
    {{event}}  e.g. kill
    {{server.name}}  e.g. My DayZ Server
    {{server.ip}}  e.g. 203.0.113.10
    {{server.port}}  e.g. 27016
    {{server.map}}  e.g. chernarusplus
    {{players}}  e.g. 12
    {{time.iso}}  e.g. 2026-09-29T18:04:00.000Z
    {{time.unix}}  e.g. 1790705040
    {{time.date}}  e.g. 2026-09-29
    {{time.time}}  e.g. 18:04:00

  hit
    {{victim.name}}  e.g. Survivor
    {{victim.id}}  e.g. 76561198000000001
    {{victim.pos}}  e.g. 7500.1, 290.5, 7700.2
    {{source.name}}  e.g. Bandit
    {{source.id}}  e.g. 76561198000000002
    {{source.kind}}  e.g. player
    {{weapon}}  e.g. M4-A1
    {{ammo}}  e.g. Bullet_556x45
    {{zone}}  e.g. Torso
    {{distance}}  e.g. 61.4
    {{health}}  e.g. 72.5
    {{details}}  e.g. Survivor (7500, 7700) hit by Bandit (7560, 7712) into Torso(72.5 HP left) with (M4-A1) from (61.4) meters
    {{event}}  e.g. hit
    {{server.name}}  e.g. My DayZ Server
    {{server.ip}}  e.g. 203.0.113.10
    {{server.port}}  e.g. 27016
    {{server.map}}  e.g. chernarusplus
    {{players}}  e.g. 12
    {{time.iso}}  e.g. 2026-09-29T18:04:00.000Z
    {{time.unix}}  e.g. 1790705040
    {{time.date}}  e.g. 2026-09-29
    {{time.time}}  e.g. 18:04:00

  join
    {{player.name}}  e.g. Survivor
    {{player.id}}  e.g. 76561198000000001
    {{action}}  e.g. joined the server!
    {{event}}  e.g. join
    {{server.name}}  e.g. My DayZ Server
    {{server.ip}}  e.g. 203.0.113.10
    {{server.port}}  e.g. 27016
    {{server.map}}  e.g. chernarusplus
    {{players}}  e.g. 12
    {{time.iso}}  e.g. 2026-09-29T18:04:00.000Z
    {{time.unix}}  e.g. 1790705040
    {{time.date}}  e.g. 2026-09-29
    {{time.time}}  e.g. 18:04:00

  leave
    {{player.name}}  e.g. Survivor
    {{player.id}}  e.g. 76561198000000001
    {{action}}  e.g. left the server!
    {{event}}  e.g. leave
    {{server.name}}  e.g. My DayZ Server
    {{server.ip}}  e.g. 203.0.113.10
    {{server.port}}  e.g. 27016
    {{server.map}}  e.g. chernarusplus
    {{players}}  e.g. 12
    {{time.iso}}  e.g. 2026-09-29T18:04:00.000Z
    {{time.unix}}  e.g. 1790705040
    {{time.date}}  e.g. 2026-09-29
    {{time.time}}  e.g. 18:04:00

  leave.early
    {{player.name}}  e.g. Survivor
    {{player.id}}  e.g. 76561198000000001
    {{action}}  e.g. disconnected early from server (EXIT NOW).
    {{event}}  e.g. leave.early
    {{server.name}}  e.g. My DayZ Server
    {{server.ip}}  e.g. 203.0.113.10
    {{server.port}}  e.g. 27016
    {{server.map}}  e.g. chernarusplus
    {{players}}  e.g. 12
    {{time.iso}}  e.g. 2026-09-29T18:04:00.000Z
    {{time.unix}}  e.g. 1790705040
    {{time.date}}  e.g. 2026-09-29
    {{time.time}}  e.g. 18:04:00

  logout.start
    {{player.name}}  e.g. Survivor
    {{player.id}}  e.g. 76561198000000001
    {{action}}  e.g. initiated disconnect process..
    {{event}}  e.g. logout.start
    {{server.name}}  e.g. My DayZ Server
    {{server.ip}}  e.g. 203.0.113.10
    {{server.port}}  e.g. 27016
    {{server.map}}  e.g. chernarusplus
    {{players}}  e.g. 12
    {{time.iso}}  e.g. 2026-09-29T18:04:00.000Z
    {{time.unix}}  e.g. 1790705040
    {{time.date}}  e.g. 2026-09-29
    {{time.time}}  e.g. 18:04:00

  logout.cancel
    {{player.name}}  e.g. Survivor
    {{player.id}}  e.g. 76561198000000001
    {{action}}  e.g. canceled logout
    {{event}}  e.g. logout.cancel
    {{server.name}}  e.g. My DayZ Server
    {{server.ip}}  e.g. 203.0.113.10
    {{server.port}}  e.g. 27016
    {{server.map}}  e.g. chernarusplus
    {{players}}  e.g. 12
    {{time.iso}}  e.g. 2026-09-29T18:04:00.000Z
    {{time.unix}}  e.g. 1790705040
    {{time.date}}  e.g. 2026-09-29
    {{time.time}}  e.g. 18:04:00

  server.status
    {{server.fps}}  e.g. 58
    {{uptime}}  e.g. 0d 5h 12m 40s
    {{uptime.seconds}}  e.g. 18760
    {{event}}  e.g. server.status
    {{server.name}}  e.g. My DayZ Server
    {{server.ip}}  e.g. 203.0.113.10
    {{server.port}}  e.g. 27016
    {{server.map}}  e.g. chernarusplus
    {{players}}  e.g. 12
    {{time.iso}}  e.g. 2026-09-29T18:04:00.000Z
    {{time.unix}}  e.g. 1790705040
    {{time.date}}  e.g. 2026-09-29
    {{time.time}}  e.g. 18:04:00

  server.boot
    {{event}}  e.g. server.boot
    {{server.name}}  e.g. My DayZ Server
    {{server.ip}}  e.g. 203.0.113.10
    {{server.port}}  e.g. 27016
    {{server.map}}  e.g. chernarusplus
    {{players}}  e.g. 12
    {{time.iso}}  e.g. 2026-09-29T18:04:00.000Z
    {{time.unix}}  e.g. 1790705040
    {{time.date}}  e.g. 2026-09-29
    {{time.time}}  e.g. 18:04:00
