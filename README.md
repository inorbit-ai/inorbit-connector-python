# `inorbit-connector`

![License](https://img.shields.io/badge/License-MIT-yellow.svg) ![PyPI - Package Version](https://img.shields.io/pypi/v/inorbit-connector) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/inorbit-connector)

![Lint and Test](https://github.com/inorbit-ai/inorbit-connector-python/actions/workflows/lint-and-test.yaml/badge.svg) ![Build and Publish](https://github.com/inorbit-ai/inorbit-connector-python/actions/workflows/build-and-publish.yaml/badge.svg) 

A Python framework for developing _connectors_ for the [InOrbit](https://inorbit.ai/) RobOps ecosystem.

## Overview

This repository contains a Python framework that provides a base structure for developing [InOrbit](https://inorbit.ai/) robot connectors.
Making use of InOrbit's [Edge SDK](https://developer.inorbit.ai/docs#edge-sdk), `inorbit-connector` provides a starting point for the integration of a fleet of robots in InOrbit, unlocking interoperability.

## Requirements

- Python 3.10 or later
- InOrbit account [(it's free to sign up!)](https://control.inorbit.ai)

## Setup

There are two ways of installing the `inorbit-connector` Python package.

1. From [PyPi](https://pypi.org/project/inorbit-connector/): `pip install inorbit-connector`

2. From source: clone the repository and install the dependencies:

```bash
git clone https://github.com/inorbit-ai/inorbit-connector-python.git
virtualenv venv
. venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

The [`examples`](examples) directory contains usage examples of the connector. See [scripts/README](scripts/README.md) for more information.

## Contributing

Any contribution that you make to this repository will be under the MIT license, as dictated by that [license](https://opensource.org/licenses/MIT).

Please refer to the [CONTRIBUTING.md](CONTRIBUTING.md) file for information on how to contribute to this project.

![Powered by InOrbit](assets/inorbit_github_footer.png)
