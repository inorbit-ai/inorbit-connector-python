---
title: "Datasource Standards"
description: "Canonical datasource contracts shared across connectors in a robot vertical"
---

Connectors for different robot brands in the same vertical (cleaning, material-moving,
...) should publish the same key-value and mission-data shape whenever the underlying
robots expose equivalent information. That's what lets InOrbit account
configuration — DataSourceDefinitions, KPI definitions, Modes, dashboards — be built once
per vertical and reused across OEMs, instead of maintaining one dialect per connector.

These pages define those shared contracts:

- [Cleaning-robot datasources](cleaning-robot-datasources)
- [Material-moving robot datasources](material-moving-robot-datasources)

When implementing a new connector in one of these verticals, publish the fields the
standard defines under their canonical names, and treat anything the robot's API can't
provide as an accepted per-OEM gap.
