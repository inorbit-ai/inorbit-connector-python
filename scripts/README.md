# Example Connector

`example.py` includes example configurations and classes for a basic connector. The example will read in custom
configuration values from `example.yaml`, create a connection to InOrbit based on the environment variables in
`example.env`, and create a custom execution loop that:

1) Publishes the connector_config as a `robot_key_value` topic
2) Publishes random CPU/RAM/HDD usage values

To run the example:

1) Create an InOrbit API Key and add it to `example.env`
2) Install the `inorbit_connector` library in a virtual environment:
    ```shell
    virtualenv .venv
    source .venv/bin/activeate
    pip install .
    ```
3) Source your environment file:
    ```shell
    source scripts/example.env
    ```
4) Run the example connector:
    ```shell
    python scripts/example.py
    ```
   
To kill the connector, use `ctrl-c` in the terminal.
