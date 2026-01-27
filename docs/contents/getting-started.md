---
title: "Getting Started"
description: "Installation and setup for the InOrbit Connector Framework"
---

## Quick Start

A cookiecutter template is available for quickly generating a new connector project. See [`inorbit-connector-cookiecutter`](https://github.com/inorbit-ai/inorbit-connector-cookiecutter) for more information.

To generate a new connector project:

1. Create a new repository and `cd` into it.
2. Run `pipx run cookiecutter gh:inorbit-ai/inorbit-connector-cookiecutter`. This will install the [cookiecutter package](https://cookiecutter.readthedocs.io/) if you don't have it already and download the InOrbit connector cookiecutter.
3. Follow the prompts to create a new connector.
4. Once all questions are answered, the cookiecutter will generate a bunch of files and directories for you to start working on your connector.
5. Read the notice at the top of the generated README.md file and follow the instructions to complete the setup.

Continue reading for a complete usage guide and examples.

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
