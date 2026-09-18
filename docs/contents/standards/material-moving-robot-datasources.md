---
title: "Material-Moving Robot Datasources"
description: "Canonical key-value and mission-data contract for material-moving (AMR) connectors"
---

Autonomous mobile robots (AMRs) that move material between locations — pickup/dropoff,
delivery, multi-goal missions — expose very different vendor APIs, but operators need the
same picture regardless of brand: is the robot idle, moving, charging, or stopped; how far
has it gone; how did the last mission go. This standard defines a shared set of
snake_case keys for the material-moving vertical, following the same conventions as the
[cleaning-robot standard](cleaning-robot-datasources), so that account configuration
(DataSourceDefinitions, KPI definitions, Modes, dashboards) can be built once and reused
across OEMs instead of maintaining a separate dialect per connector.

When a robot's API can't provide a field, the connector omits it rather than
guessing — the field stays part of the contract for every other connector that can
provide it.

## Conventions

Same platform-wide conventions the cleaning-robot standard uses:

- Keys are `snake_case`, identical across OEMs.
- Percentages are published as **0–1**.
- Units are SI: m, s, m/s, kg where applicable.
- Unit suffix grammar: plain unit as-is (`_m`, `_s`), percentages `_pct` (0–1), counts
  `_count`, rates join with `p` for "per".
- Fields normalized to an InOrbit enum publish twice: the normalized value under the
  canonical key, and the untouched vendor value under `<field>_raw`. Unrecognized vendor
  values normalize to `"other"` or `"unknown"`, while the raw key still shows exactly what
  the robot reported. A value derived from *several* fields (like `mission_status`) has no
  `_raw` twin, since there's no single raw value to preserve — its inputs remain visible
  under their own keys.
- Numeric fields have no `_raw` twin.
- Omit rather than guess: an unrecognized enum value omits the canonical key only when
  even `"other"`/`"unknown"` would be misleading; a derived figure whose arithmetic
  doesn't hold is withheld rather than published wrong.

### The `mission_tracking` envelope

Connectors publish mission data inside a JSON-typed key-value named `mission_tracking`,
shaped as `{missionId, inProgress, status, state, label, completedPercent, startTs,
endTs?, data: {...}, tasks?: [...]}`. That envelope is fixed by InOrbit's
`MissionTracking`/Mission-object schema, not a per-connector choice, so it's out of scope
for this standard. **Homogenization targets the inner `data{}` dict**, which is
connector-authored, plus the vendor vocabularies feeding the envelope's own `state` and
`status` fields (below).

## Live key-values

| Key | Unit/Type | Meaning |
|---|---|---|
| `connector_version` | string | Connector build version |
| `api_connected` | bool | Connector-to-vendor-API reachability |
| `robot_online` | bool | Robot connectivity, distinct from API reachability |
| `battery_pct` | 0–1 | Battery level |
| `battery_time_remaining_s` | s | Estimated time until battery depletion |
| `task_state` | enum + raw | `idle`, `executing`, `paused`, `unknown` — the robot's own execution state |
| `mission_status` | enum string | Fleet-wide operating mode; drives the Modes panel (see below) |
| `emergency_stop` | bool | E-stop engaged (omitted, not `false`, on hardware/firmware that can't report it) |
| `distance_to_next_target_m` | m | Distance remaining to the current target |
| `odometer_m` | m | Lifetime distance traveled (distinct from the per-mission `distance_m` mission field below) |

A robot platform is free to publish additional live key-values beyond this list
(diagnostics, Wi-Fi signal, per-sensor status) using the same naming scheme; those stay
vendor-specific rather than being forced into a shared name.

## Robot modes (`mission_status`)

Derived **inside each connector** from that robot's own state, using the same four-value
vocabulary and precedence order as the cleaning-robot standard (`Error` outranks
`Mission` outranks `Charging` outranks `Idle`):

| Mode | Meaning |
|---|---|
| `Error` | E-stop, fault, or disconnected states |
| `Mission` | Actively executing a task |
| `Charging` | On the charger, no task running |
| `Idle` | Powered and reachable, no task, not charging (fallback for unrecognized states) |

Deriving `mission_status` in the connector — instead of with an account-level derived
datasource — keeps account configuration robot-agnostic and avoids the derived datasource
silently shadowing a value the connector later starts publishing itself.

There's no `_raw` twin for `mission_status`, for the same reason as in the cleaning-robot
standard: it's derived from more than one field. Its inputs (`task_state_raw`,
`emergency_stop`) remain the debugging path.

## `task_state` vendor vocabulary

`task_state` normalizes each robot's own status vocabulary down to four values:

| Contract value | Typical vendor states |
|---|---|
| `idle` | Available, parked, allocated/unallocated, no active task |
| `executing` | Driving, en route to pickup/dropoff, in transit between waypoints |
| `paused` | Explicitly paused/interrupted, distinct from idle |
| `unknown` | Anything unrecognized |

Docking/charging substates and fault substates aren't `task_state` values — they feed
`mission_status`'s `Charging`/`Error` buckets instead. This mirrors the split the
cleaning-robot standard makes between `task_state` (robot-execution state) and
`mission_status` (the Modes-panel bucket).

## Pose

x, y in meters, yaw in radians. Vendor APIs that report position in millimeters or
orientation in degrees convert once at the connector boundary; nothing downstream ever
sees a non-SI unit.

`frame_id` should be the actual current map identifier the robot is localized on — not a
constant placeholder — so that multi-map fleets resolve poses onto the right map.

## Mission tracking data

### Envelope `state` (canonical, robot/vendor-agnostic mission lifecycle)

| Contract value | Meaning |
|---|---|
| `queued` | Mission accepted, not yet started |
| `executing` | Mission in progress |
| `paused` | Mission paused mid-execution |
| `completed` | Mission finished successfully |
| `aborted` | Mission stopped by user/operator action |
| `failed` | Mission stopped due to an error condition |
| `canceled` | Mission canceled before or during execution (vendor spelling variants collapse to this one value) |
| `unknown` | Anything unrecognized |

### Envelope `status` (mission health)

Three-value set: `ok`, `warning`, `error`. A connector that can only distinguish
success/failure publishes just `ok`/`error` and omits `warning` until it has a concrete
signal for a degraded-but-completed outcome — a narrower vocabulary is an accepted
per-OEM gap, not an error.

### Inner `data{}` mission fields

| Key | Meaning |
|---|---|
| `mission_type` / `mission_type_raw` | Normalized mission type (`pickup`, `dropoff`, `delivery`, `multi_goal`, `other`), for platforms whose API exposes one |
| `priority` | Vendor-reported mission priority, published as-is |
| `mission_steps_count` | Total segment/waypoint count for the mission |
| `distance_m` | Distance traveled **during this mission only** — must reset per mission. Watch out for accidentally publishing the lifetime `odometer_m` value here instead, since it looks correct until a robot runs a second mission |
| `duration_s` | Wall time from mission start to end |
| `interruptions_count` | Number of times the mission transitioned from `executing` to `paused` |

`data{}` should carry only fields whose meaning changes per mission. Connector-context
fields that don't vary by mission (robot model, serial number, uptime) belong in live
key-values, not inside a mission report — duplicating them per mission adds noise without
adding information.

## Config as code

Both `mission_status` and `task_state` are plain `keyValue` DataSourceDefinitions (no
transform needed) once the connector computes and publishes them directly — the same
shape used by the cleaning-robot standard's `mission_status` example. Deriving these at
the account-config layer instead of in the connector is discouraged for the same reason
called out above: a derived datasource can end up shadowing a value the connector
publishes natively, and it duplicates logic that's easier to keep correct in one place per
connector.
