# Configuration

Use `ConnectorConfig` (Pydantic) with a `fleet` of `RobotConfig` entries.

Key fields:
- `api_key`, `api_url`
- `connector_type`, `connector_config` (your custom model)
- `update_freq`, `location_tz`
- `logging` (config file path and log level)
- `maps` (frame_id -> map metadata)
- `env_vars` (env passed to connector/user scripts)
- `fleet` (list of robots with `robot_id`, `cameras`)

Environment variables:
- `INORBIT_API_KEY` (required)
- `INORBIT_API_URL` (optional)

See `examples/example.yaml` and `examples/example.fleet.yaml`.

