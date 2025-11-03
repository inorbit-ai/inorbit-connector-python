# Getting Started

## Installation

Install the package from PyPI:

```bash
pip install inorbit-connector
```

Or from source (development):

```bash
git clone https://github.com/inorbit-ai/inorbit-connector-python.git
cd inorbit-connector-python
pip install .
```

## Requirements

- Python 3.10+
- InOrbit account (`https://control.inorbit.ai`)
- InOrbit API key exported as `INORBIT_API_KEY`

```bash
export INORBIT_API_KEY="<your_api_key>"
```

## Run the examples

The `examples/` directory contains runnable samples.

```bash
cd examples
source example.env
python simple-connector/connector.py
```

