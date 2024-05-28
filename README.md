# inorbit-connector-python
A Python library for developing connectors the InOrbit RobOps ecosystem.


|   OS    |                                                                                                                                                                            Python 3.10                                                                                                                                                                            |                                                                                                                                                                            Python 3.11                                                                                                                                                                            |
|:-------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|
|  Linux  |   [![TeamCity](https://inorbit.teamcity.com/app/rest/builds/buildType:id:Engineering_Development_DeveloperPortal_InorbitConnectorPython_LinuxPython310QualityCheck/statusIcon.svg)](https://inorbit.teamcity.com/buildConfiguration/Engineering_Development_DeveloperPortal_InorbitConnectorPython_LinuxPython310QualityCheck?branch=%3Cdefault%3E&mode=builds)   |   [![TeamCity](https://inorbit.teamcity.com/app/rest/builds/buildType:id:Engineering_Development_DeveloperPortal_InorbitConnectorPython_LinuxPython311QualityCheck/statusIcon.svg)](https://inorbit.teamcity.com/buildConfiguration/Engineering_Development_DeveloperPortal_InorbitConnectorPython_LinuxPython311QualityCheck?branch=%3Cdefault%3E&mode=builds)   |
|  MacOS  |     [![TeamCity](https://inorbit.teamcity.com/app/rest/builds/buildType:id:Engineering_Development_DeveloperPortal_InorbitConnectorPython_MacPython310QualityCheck/statusIcon.svg)](https://inorbit.teamcity.com/buildConfiguration/Engineering_Development_DeveloperPortal_InorbitConnectorPython_MacPython310QualityCheck?branch=%3Cdefault%3E&mode=builds)     |     [![TeamCity](https://inorbit.teamcity.com/app/rest/builds/buildType:id:Engineering_Development_DeveloperPortal_InorbitConnectorPython_MacPython311QualityCheck/statusIcon.svg)](https://inorbit.teamcity.com/buildConfiguration/Engineering_Development_DeveloperPortal_InorbitConnectorPython_MacPython311QualityCheck?branch=%3Cdefault%3E&mode=builds)     |
| Windows | [![TeamCity](https://inorbit.teamcity.com/app/rest/builds/buildType:id:Engineering_Development_DeveloperPortal_InorbitConnectorPython_WindowsPython310QualityCheck/statusIcon.svg)](https://inorbit.teamcity.com/buildConfiguration/Engineering_Development_DeveloperPortal_InorbitConnectorPython_WindowsPython310QualityCheck?branch=%3Cdefault%3E&mode=builds) | [![TeamCity](https://inorbit.teamcity.com/app/rest/builds/buildType:id:Engineering_Development_DeveloperPortal_InorbitConnectorPython_WindowsPython311QualityCheck/statusIcon.svg)](https://inorbit.teamcity.com/buildConfiguration/Engineering_Development_DeveloperPortal_InorbitConnectorPython_WindowsPython311QualityCheck?branch=%3Cdefault%3E&mode=builds) |
| Qodana  |      [![TeamCity](https://inorbit.teamcity.com/app/rest/builds/buildType:id:Engineering_Development_DeveloperPortal_InorbitConnectorPython_QodanaLinuxQualityCheck/statusIcon.svg)](https://inorbit.teamcity.com/buildConfiguration/Engineering_Development_DeveloperPortal_InorbitConnectorPython_QodanaLinuxQualityCheck?branch=%3Cdefault%3E&mode=builds)      |                                                                                                                                                                                --                                                                                                                                                                                 |

## Overview

This repository contains a Python library for creating [InOrbit](https://inorbit.ai/) robot connectors.
Making use of InOrbit's [Edge SDK](https://developer.inorbit.ai/docs#edge-sdk), the library allows the integration of
your fleet of robots in InOrbit, unlocking interoperability.

## Requirements

- Python 3.10 or later
- InOrbit account [(it's free to sign up!)](https://control.inorbit.ai)
## Setup

There are two ways for installing the connector Python package.

1. From PyPi: `pip install inorbit-connector-python`

2. From source: clone the repository and install the dependencies:

```bash
cd instock_connector/
virtualenv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Getting Started

See [scripts/README](scripts/README.md) for usage of an example connector.
