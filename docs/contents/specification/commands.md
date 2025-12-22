---
title: "Commands Utilities"
description: "Command handling utilities specification"
---

This page specifies command handling helpers from `inorbit_connector.commands`.

(spec-commands-commandfailure)=
## `CommandResultCode` / `CommandFailure`

- `CommandResultCode` is an enum with `SUCCESS` and `FAILURE`.
- `CommandFailure` is an exception that carries:
  - `execution_status_details`: a user-visible failure summary
  - `stderr`: a more detailed error payload

When `CommandFailure` is raised inside a command handler, the framework converts it into a failure result via the provided `options["result_function"]`.

(spec-commands-parse-custom-command-args)=
## `parse_custom_command_args(custom_command_args) -> (script_name, params)`

Parses arguments for a `COMMAND_CUSTOM_COMMAND`/RunScript-style payload.

Input assumptions:

- `custom_command_args[0]` is a script name (string).
- `custom_command_args[1]` is a list-like container with alternating `key, value, key, value, ...`.

Output:

- `script_name`: string
- `params`: dictionary of parsed key/value pairs (last value wins on duplicate keys)

Raises:

- `ValueError` when the outer container does not match the expected types/shapes.
- `CommandFailure` when the arguments list is not pairs (odd length).

(spec-commands-commandmodel)=
## `CommandModel` / `ExcludeUnsetMixin`

These classes support type-safe parsing and validation of structured command parameters.

- `CommandModel` is a Pydantic `BaseModel` configured with `extra="forbid"`, and converts `ValidationError` into `CommandFailure`.
- `ExcludeUnsetMixin` changes `model_dump()` default behavior to `exclude_unset=True` (useful when you want to emit only explicitly-provided fields).

See [Commands Handling](../usage/commands-handling) for end-to-end usage patterns.

## Note: re-exports via `inorbit_connector.connector`

For backwards compatibility, the connector module re-exports:

- `CommandFailure`
- `CommandResultCode`
- `parse_custom_command_args`

New code may import from either module, but the canonical definitions live in `inorbit_connector.commands`.


