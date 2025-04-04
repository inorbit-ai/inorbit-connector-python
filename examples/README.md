# Connector Examples

This directory contains examples of connectors that can be used as a starting point for developing your own connectors.

## `simple-connector/` 

The contents of this directory demonstrate the basic usage of the `inorbit-connector` library. It can be run with the following command:

```bash
python simple-connector/simple_connector.py
```

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
pip install .
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
+ A mock robot API class, which simulates a robot sending data to the connector
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

![Powered by InOrbit](../assets/inorbit_github_footer.png)
