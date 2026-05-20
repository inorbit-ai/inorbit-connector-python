---
title: "Utilities"
description: "Utility functions specification"
---

This page specifies utilities from `inorbit_connector.utils`.

(spec-utils-readyaml)=
## `read_yaml(fname) -> dict`

Reads a YAML file and returns a dictionary.

Behavior:

- If the file is empty (YAML `null` / no content), returns `{}`.
- Otherwise, returns the parsed YAML content.

## Constants

- `DEFAULT_TIMEZONE`: default timezone string (`"UTC"`).
- `DEFAULT_LOGGING_CONFIG`: path to the package default logging config file.


