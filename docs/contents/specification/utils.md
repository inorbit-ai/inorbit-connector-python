---
title: "Utilities"
description: "Utility functions specification"
---

This page specifies utilities from `inorbit_connector.utils`.

(spec-utils-readyaml)=
## `read_yaml(fname, robot_id=None) -> dict`

Reads a YAML file and returns a dictionary.

Behavior:

- If the file is empty (YAML `null` / no content), returns `{}`.
- If `robot_id` is **not** provided, returns the entire YAML object.
- If `robot_id` **is** provided and is a top-level key in the YAML object, returns `data[robot_id]` and emits a **DeprecationWarning** (this selection format is deprecated).
- If `robot_id` is provided but not found, raises `IndexError`.

Notes:

- New configurations should follow the `ConnectorConfig` schema described in [Configuration](/ground-control/robot-integration/connector-framework/configuration).

## Constants

- `DEFAULT_TIMEZONE`: default timezone string (`"UTC"`).
- `DEFAULT_LOGGING_CONFIG`: path to the package default logging config file.


