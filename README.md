# inorbit-connector-python

![License](https://img.shields.io/badge/License-MIT-yellow.svg) ![PyPI - Package Version](https://img.shields.io/pypi/v/inorbit-connector) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/inorbit-connector)

![Lint and Test](https://github.com/inorbit-ai/inorbit-connector-python/actions/workflows/lint-and-test.yaml/badge.svg) ![Build and Publish](https://github.com/inorbit-ai/inorbit-connector-python/actions/workflows/build-and-publish.yaml/badge.svg) 

A Python library for developing connectors the InOrbit RobOps ecosystem.

## Overview

This repository contains a Python library for creating [InOrbit](https://inorbit.ai/) robot connectors.
Making use of InOrbit's [Edge SDK](https://developer.inorbit.ai/docs#edge-sdk), the library allows the integration of
your fleet of robots in InOrbit, unlocking interoperability.

## Requirements

- Python 3.10 or later
- InOrbit account [(it's free to sign up!)](https://control.inorbit.ai)
## Setup

There are two ways for installing the connector Python package.

1. From PyPi: `pip install inorbit-connector`

2. From source: clone the repository and install the dependencies:

```bash
cd instock_connector/
virtualenv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Getting Started

See [scripts/README](scripts/README.md) for usage of an example connector.
