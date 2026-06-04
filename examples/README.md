<!--
SPDX-FileCopyrightText: 2025 InOrbit, Inc.

SPDX-License-Identifier: MIT
-->

# Connector Examples

This directory contains examples of connectors that can be used as a starting point for developing your own connectors.

## `simple-connector/`

The contents of this directory demonstrate the basic usage of the `inorbit-connector` framework. 

It includes example configurations and classes for a basic connector. The example will read in custom
configuration values from `example.yaml`, create a connection to InOrbit based on the environment variables in
`example.env`, and create a custom execution loop that:

1) Publishes the connector_config as a `robot_key_value` topic
2) Publishes random CPU/RAM/HDD usage values

To run the example:

1) Create an InOrbit API Key and add it to `example.env`
2) Install the `inorbit_connector` library in a virtual environment:

```shell
virtualenv .venv
source .venv/bin/activate
pip install .[colorlog]
```

3) Source your environment file:

```shell
cd examples/
source example.env
```

4) Run the example connector:

```shell
python simple-connector/connector.py
```

To kill the connector, press `ctrl-c` in the terminal.

## `robot-connector/`

This directory contains a more comprehensive example of a connector. In addition to the contents of the `simple-connector` demo, it includes:

+ An entry point script with custom argument parsing
+ A mock robot API class, which simulates a robot's polling API for fetching real-time data
+ A connector class that publishes the robot data to InOrbit
+ Connector configuration classes with custom fields for the robot
+ TO-DO: A custom commands handler
+ TO-DO: An integration with the [`inorbit_edge_executor`](https://pypi.org/project/inorbit-edge-executor/) for mission execution.

It is run in the same way as the `simple-connector` example, with the robot selection being done through the command line:

```shell
cd examples/
source example.env
python robot-connector/main.py --help
python robot-connector/main.py --config example.yaml --robot_id my-example-robot
```

To kill the connector, press `ctrl-c` in the terminal.


## `simple-fleet-connector/`

This directory contains a simple, single-file example of a **fleet connector** that demonstrates how to manage multiple robots using the `FleetConnector` base class.

The simple fleet connector shows how to:

+ Manage a fleet of multiple robots (reads from `example.fleet.yaml`)
+ Fetch data for all robots concurrently using `asyncio.gather()`
+ Use robot-specific publishing methods like `publish_robot_pose(robot_id, ...)`
+ Handle commands for specific robots in the fleet
+ Use the fleet configuration file format with `common` and `robots` sections

Key differences from single robot connectors:
- Inherits from `FleetConnector` instead of `Connector`
- Takes a list of `robot_ids` instead of a single `robot_id`
- Uses robot-specific publishing methods (e.g., `publish_robot_pose(robot_id, ...)`)
- Command handler receives `robot_id` as the first parameter
- Reads configuration from `example.fleet.yaml` with `common` section and `robots` array

To run the simple fleet connector:

```shell
cd examples/
source example.env
python simple-fleet-connector/connector.py
```

To kill the connector, press `ctrl-c` in the terminal.


## `fleet-connector/`

This directory contains a more comprehensive example of a **fleet connector** that demonstrates how to manage multiple robots using the `FleetConnector` base class. Similar to the `robot-connector` example, it includes:

+ An entry point script with custom argument parsing
+ A mock fleet manager API class, which simulates polling a fleet management system for data about multiple robots in the fleet
+ A connector class that publishes data for all robots in the fleet to InOrbit
+ Proper separation of concerns with datatypes, fleet client, and connector modules
+ Robot-specific command handling for each robot in the fleet

Configuration file structure (`example.fleet.yaml`):
```yaml
common:
  # Common configuration for all robots
  connector_type: example_bot
  update_freq: 1.0
  # ... other common settings
  connector_config:
    example_bot_api_version: v1
    # ... custom fields

robots:
  - fleet-robot-1
  - fleet-robot-2
  - fleet-robot-3
```

To run the fleet connector example:

```shell
cd examples/
source example.env
python fleet-connector/main.py --config example.fleet.yaml
```

To kill the connector, press `ctrl-c` in the terminal.

## Metrics

The `robot-connector/` and `fleet-connector/` examples both ship with a small `metrics.py` module that demonstrates how concrete connectors declare domain instruments via `inorbit_connector.metrics.get_connector_meter`, and how to route outbound HTTP calls through the framework's canonical helpers (`record_upstream_http_request` / `record_upstream_http_error` plus `EndpointMapper` for normalization) in `robot.py` / `fleet_client.py`. Both `example.yaml` and `example.fleet.yaml` include a `metrics:` block (ports 9090 and 9091 respectively) so the connectors expose `/metrics` when run.

After starting either example, scrape the endpoint:

```shell
curl http://127.0.0.1:9090/metrics    # robot-connector
curl http://127.0.0.1:9091/metrics    # fleet-connector
```

You'll see the framework signals (`inorbit_connector_up`, `inorbit_connector_execution_loop_ticks_total`, `inorbit_connector_execution_loop_errors_total`), the canonical upstream-HTTP family from `inorbit_connector.metrics.http` (`inorbit_connector_upstream_http_requests_total{vendor="example_bot", method="GET", endpoint="..."}` and the matching `_errors_total` / `_duration_seconds_*` series), the SDK's per-robot publish counters (`calls_publish_pose_total{robot_id="..."}`, etc.), and any connector-specific domain counters declared via `get_connector_meter` (e.g. `inorbit_connector_example_bot_telemetry_invalid_response_total`). Every series carries `inorbit_connector_type` and `inorbit_connector_id` labels so cross-connector queries work on a single descriptor per metric.

For the full guide on what to instrument and why, see [the Metrics doc](../docs/contents/usage/metrics.md).

For a reference OTel collector deployment that scrapes connector `/metrics` endpoints, see [`metrics/`](metrics/).

![Powered by InOrbit](../assets/inorbit_github_footer.png)
