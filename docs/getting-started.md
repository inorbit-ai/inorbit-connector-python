<!--
SPDX-FileCopyrightText: 2025 InOrbit, Inc.

SPDX-License-Identifier: MIT
-->

# Getting Started

## Installation

There are two ways of installing the `inorbit-connector` Python package.

### From PyPI

Install the package from [PyPI](https://pypi.org/project/inorbit-connector/):

```bash
pip install inorbit-connector
```

### From Source

Clone the repository and install the dependencies:

```bash
git clone https://github.com/inorbit-ai/inorbit-connector-python.git
cd inorbit-connector-python
virtualenv venv
. venv/bin/activate
pip install .
```

Refer to the Github repository at [github.com/inorbit-ai/inorbit-connector-python](https://github.com/inorbit-ai/inorbit-connector-python) details.

## Requirements

- **Python 3.10 or later**
- **InOrbit account**: [Sign up for free](https://control.inorbit.ai)
- **InOrbit API key**: Export as `INORBIT_API_KEY` environment variable

```bash
export INORBIT_API_KEY="<your_api_key>"
```

## Run the Examples

The [`examples`](https://github.com/inorbit-ai/inorbit-connector-python/tree/main/examples) directory contains usage examples of the connector. See [examples/README](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/README.md) for more information.

### Simple Connector Example

The simplest example demonstrates basic connector functionality:

```bash
cd examples
source example.env
python simple-connector/connector.py
```

To stop the connector, press `Ctrl+C` in the terminal.

### Robot Connector Example

A more comprehensive example with command-line interface:

```bash
cd examples
source example.env
python robot-connector/main.py --config example.yaml --robot_id my-example-robot
```

### Fleet Connector Example

For managing multiple robots:

```bash
cd examples
source example.env
python fleet-connector/main.py --config example.fleet.yaml
```

## Next Steps

- Review the [Specification](specification/index) to understand the public API of the package
- Read the [Usage Guide](usage/index) to learn how to implement your own connector
- Review the [Configuration Guide](configuration) to understand connector configuration
- Check the [Publishing Guide](publishing) to learn how to publish data to InOrbit
