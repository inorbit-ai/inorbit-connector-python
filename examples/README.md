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

![Powered by InOrbit](../assets/inorbit_github_footer.png)
