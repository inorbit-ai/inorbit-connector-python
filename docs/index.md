<!--
SPDX-FileCopyrightText: 2025 InOrbit, Inc.

SPDX-License-Identifier: MIT
-->

# inorbit-connector

A Python framework for developing *connectors* for the [InOrbit](https://inorbit.ai/) RobOps ecosystem.

## Overview

This framework provides a base structure for developing [InOrbit](https://inorbit.ai/) robot connectors. Making use of InOrbit's [Edge SDK](https://developer.inorbit.ai/docs#edge-sdk), `inorbit-connector` provides a starting point for the integration of a fleet of robots in InOrbit, unlocking interoperability.

The framework supports both single-robot and fleet connectors:

- **Single-robot connectors**: Subclass `Connector` to manage one robot at a time
- **Fleet connectors**: Subclass `FleetConnector` to manage multiple robots simultaneously, ideal for managing robots through a fleet manager

Both connector types provide:
- Automatic InOrbit robot provisioning
- Built-in publishing methods for pose, odometry, key-values, and system stats
- Command handling infrastructure for receiving commands from InOrbit
- Map management with automatic updates
- Camera feed registration
- User scripts support for custom command execution
- Configurable logging

## Requirements

- Python 3.10 or later
- InOrbit account ([it's free to sign up!](https://control.inorbit.ai))

```{toctree}
:maxdepth: 2
:hidden:

getting-started
usage/index
configuration
publishing
```

## Documentation Sections

- **Getting Started**: Installation, environment setup, and running a connector
- **Usage**: Detailed guides for implementing single-robot and fleet connectors
- **Configuration**: Complete connector customization guide
- **Publishing**: How to publish data to InOrbit
