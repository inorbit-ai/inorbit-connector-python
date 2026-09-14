---
title: "Cleaning-Robot Datasources"
description: "Canonical key-value and mission-data contract for cleaning-robot connectors"
---

Cleaning robots differ a lot between manufacturers, but the operational questions fleet
operators ask are the same regardless of brand: how much area got cleaned, how full is the
water tank, is the robot charging or stuck. This standard defines a single set of
snake_case keys that any cleaning-robot connector can publish, so that InOrbit account
configuration — DataSourceDefinitions, KPI definitions, dashboards, per-zone coverage —
can be built once and reused unchanged across OEMs.

When a given robot's API can't provide a field, the connector simply omits it. The field
stays part of the contract for every other connector that can.

## Conventions

- Keys are `snake_case` and identical across OEMs.
- Percentages are always published normalized to **0–1** (InOrbit's platform convention:
  `%` datasources store 0–1 and widgets multiply by 100 for display). A vendor API that
  reports 0–100 is adapted at the connector or via a `scale: 0.01` tag definition.
- Units are SI (m², s, L, km/h).
- Unit suffixes on keys follow a fixed grammar:
  - plain unit as-is — `_m2`, `_s`, `_l`
  - percentages — `_pct` (values 0–1)
  - counts — `_count`
  - rates join with `p` for "per" — `_m2ph` for m²/h, `_kmph` for km/h (never `_kmh`)
- **Enum fields publish two keys.** A field normalized to an InOrbit-standard enum (for
  example `cleaning_mode` or `task_outcome`) is published twice: the normalized value
  under the canonical key, and the vendor's original value untouched under `<field>_raw`.
  For example, a robot dust-mopping publishes `cleaning_mode: "dust_mop"` alongside
  `cleaning_mode_raw: "__尘推"` (the vendor's own string). When a vendor sends a value the
  mapping doesn't recognize, the normalized key falls back to `"other"` while the raw key
  still shows exactly what the robot reported — so unrecognized values stay visible (and
  bucketable in dashboards) instead of disappearing, and mapping bugs stay debuggable.
  Numeric fields have no `_raw` twin.
- Mission fields are scalars, so they're KPI-definable with no platform changes.

## Mission report fields

Published once at the end of a task, as part of the connector's `mission_tracking` data.
These aren't standalone datasources — they land in mission data and feed KPI definitions.

| Key | Unit | Meaning |
|---|---|---|
| `planned_area_m2` | m² | Area the task was supposed to clean |
| `cleaned_area_m2` | m² | Area actually cleaned |
| `coverage_pct` | 0–1 | `cleaned_area_m2` / `planned_area_m2` |
| `duration_s` | s | Wall time, start to end |
| `active_cleaning_time_s` | s | Time actually spent cleaning (excludes pauses/interruptions) |
| `efficiency_m2ph` | m²/h | Cleaned area per active hour |
| `water_used_l` | L | Water consumed |
| `battery_start_pct` | 0–1 | Battery level at task start |
| `battery_end_pct` | 0–1 | Battery level at task end |
| `battery_used_pct` | 0–1 | Battery consumed during the task |
| `interruptions_count` | count | Pauses/breaks during the task |
| `cleaning_mode` | enum + raw | `scrub`, `vacuum`, `sweep`, `dust_mop`, `polish`, `disinfect`, `other` |
| `task_outcome` | enum | `completed`, `incomplete`, `abandoned`, `not_reported` |
| `map_name` | string | Map(s)/floor(s) the task ran on (comma-joined) — a free group-by dimension |
| `report_image_url` | url | Vendor-rendered coverage/report image |

`task_outcome` compares reported coverage against a configurable success threshold to
decide `completed` vs. `incomplete`.

Per-zone coverage fields (`zone_<slug>_planned_m2`, `zone_<slug>_actual_m2`,
`zone_<slug>_pct`) follow the same naming pattern alongside these.

## Live (timeline) datasources

Published continuously for basic observability.

| Key | Unit | Meaning |
|---|---|---|
| `battery_pct` | 0–1 | Battery level |
| `charging` | bool | On charger and charging |
| `task_state` | enum | `idle`, `cleaning`, `paused`, `unknown` |
| `robot_online` | bool | Robot connectivity (not API health) |
| `current_map_name` | string | Map/floor the robot is localized on |
| `clean_water_tank_pct` | 0–1 | Fresh/solution tank level (robots that only expose a boolean publish 0 or 1) |
| `recovery_tank_pct` | 0–1 | Sewage/recovery tank level (same fallback as above) |
| `emergency_stop` | bool | E-stop engaged |
| `speed_kmph` | km/h | Current speed |
| `mission_status` | enum string | Robot operating mode; drives the fleet-wide Modes panel (see below) |

High-value optional fields, published when the robot's API exposes them: per-part
consumable wear (`consumable_<part>_wear_pct`), battery health (`battery_soh`,
`battery_cycles`), and live task progress (cleaned m² so far).

## Robot modes (`mission_status`)

The Modes panel accepts any string, so this contract doesn't enforce a fixed vocabulary —
but the recommended approach is a standard mode enum, derived **inside each connector**
from that robot's own state fields and published as `mission_status`:

| Mode | Meaning |
|---|---|
| `Idle` | Powered and reachable, no task running, not charging |
| `Mission` | Running a cleaning task (a paused task counts as `Mission` unless a connector distinguishes `Paused`) |
| `Paused` | Optional: task paused, for connectors that can distinguish it |
| `Charging` | On the charger with no task running (`Mission` outranks `Charging`) |
| `Error` | E-stop, stuck, disabled, or other fault states |

Deriving `mission_status` in the connector — rather than with an account-level derived
datasource — keeps account configuration robot-agnostic and makes the Modes panel a
trivial one-to-one mapping. The robot's raw vendor state remains available through
`task_state` for debugging.

## Optional, vendor-specific fields

Connectors are free to publish additional fields using the same naming scheme when a
robot's API supports them: `charge_stops_count`, `elevator_rides_count`,
`coverage_heatmap_url`, per-part consumable percentages
(`consumable_brush_pct`, `consumable_filter_pct`, `consumable_suction_blade_pct`),
`polished_area_planned_m2` / `polished_area_m2`, `operator`, `distance_m`.

A few fields are deliberately left out of the standard contract:

- **Energy consumption (`energy_kwh`)** — not consistently available or reliable across
  vendors; battery-level deltas already cover this need.
- **Distance as a common field** — the platform derives `estimatedDistance` from pose
  data where poses are published, so vendor-reported distance is treated as an optional
  extra rather than a canonical field.
- **Tank levels as mission-report fields** — tank levels are live datasources, not
  end-of-task figures, since they don't reset per mission.

## Example: mapping a real connector

As a concrete example, here's how the [Gausium
connector](https://github.com/inorbit-ai/inorbit-robot-connectors) (Scrubber 50, Open
Platform API) maps this contract onto its vendor API:

| Contract key | Gausium source |
|---|---|
| `planned_area_m2` / `cleaned_area_m2` | `plannedCleaningAreaSquareMeter` / `actualCleaningAreaSquareMeter` |
| `coverage_pct` | `completionPercentage` (already 0–1) |
| `duration_s` | `endTime − startTime` |
| `active_cleaning_time_s` | `durationSeconds` |
| `efficiency_m2ph` | `efficiencySquareMeterPerHour` |
| `water_used_l` | `waterConsumptionLiter` |
| `battery_start_pct` / `battery_end_pct` / `battery_used_pct` | `startBatteryPercentage` / `endBatteryPercentage` / their difference (0–100, scaled to 0–1) |
| `interruptions_count` | Counted from RUNNING → PAUSED transitions |
| `cleaning_mode` | `cleaningMode`, mapped through a translation table |
| `task_outcome` | Derived from `taskEndStatus` plus the success threshold |
| `map_name` | `subTasks[].mapName` |
| `report_image_url` | `taskReportPngUri` |
| `battery_pct` / `charging` | `battery.powerPercentage` (scaled to 0–1) / `battery.charging` |
| `task_state` | `taskState` |
| `robot_online` | `online` |
| `current_map_name` | `localizationInfo.map.name` |
| `clean_water_tank_pct` / `recovery_tank_pct` | `device.cleanWaterTank.level` / `device.recoveryWaterTank.level` |
| `emergency_stop` | `emergencyStop.enabled` |
| `speed_kmph` | `speedKilometerPerHour` |
| `mission_status` | Derived from `taskState`, `battery.charging`, and `emergencyStop.enabled` |

This mapping generalizes to any cleaning robot exposing an equivalent set of status and
report fields — the contract itself doesn't change per vendor, only the source-field
lookup does.

## Account configuration example

A typical setup uses one account-scoped `mission_tracking` fallback datasource, plus one
derived datasource per field:

```yaml
kind: DataSourceDefinition
metadata:
  scope: <CONFIG_SCOPE>
  id: cleaned_area_m2
apiVersion: v0.1
spec:
  label: Cleaned area
  unit: "m2"
  timeline: {}
  source:
    derived:
      transform: |
        mt = getValue("mission_tracking");
        mt.data.cleaned_area_m2
```

For percent datasources, always set `scale` explicitly. With `unit: "%"` and no `scale`,
the platform defaults to `scale: 0.01` and re-scales an already-normalized 0–1 value.
Use `scale: 1` for keys that are already 0–1, and `scale: 0.01` only when adapting a
legacy 0–100 source.
