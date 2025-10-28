#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import asyncio
from typing import Callable, Coroutine

# InOrbit
from inorbit_connector.connector import Connector, CommandResultCode
from inorbit_connector.models import InorbitConnectorConfig


class ManagedConnector(Connector):
    """A connector that is managed by an external Fleet.

    This connector does not manage its own thread or event loop. Instead, it is
    designed to be managed by a Fleet instance that provides the event loop and
    orchestrates multiple connectors.

    The execution loop is delegated to the Fleet, which calls the connector's
    methods at the appropriate times.
    """

    def __init__(self, robot_id: str, config: InorbitConnectorConfig, **kwargs) -> None:
        """Initialize a managed connector.

        Args:
            robot_id (str): The ID of the InOrbit robot
            config (InorbitConnectorConfig): The connector configuration

        Keyword Args:
            Same as Connector base class
        """
        # Disable automatic command handler registration - Fleet will handle it
        kwargs.setdefault("register_custom_command_handler", False)
        super().__init__(robot_id, config, **kwargs)

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach an external event loop to this connector.

        This must be called by the Fleet before the connector is started.
        Sets the mangled __loop attribute so command handlers work correctly.

        Args:
            loop (asyncio.AbstractEventLoop): The event loop to attach
        """
        # Set the private __loop attribute via name mangling
        # This is used by _register_custom_command_handler for asyncio.run_coroutine_threadsafe
        self._Connector__loop = loop

    def set_fleet_command_handler(
        self, handler: Callable[[str, str, list, dict], Coroutine]
    ) -> None:
        """Set the fleet-level command handler for this connector.

        This wraps the fleet handler to include robot_id and registers it using
        the superclass's command handler registration logic.

        The handler signature is:
            async def handler(robot_id: str, command_name: str, args: list, options: dict)

        Args:
            handler: The async command handler function from the Fleet
        """

        # Create a wrapper that includes robot_id in the call to the fleet handler
        async def fleet_command_wrapper(
            command_name: str, args: list, options: dict
        ) -> None:
            await handler(self.robot_id, command_name, args, options)

        # Use the superclass's command handler registration logic
        self._register_custom_command_handler(fleet_command_wrapper)

    async def _inorbit_command_handler(
        self, command_name: str, args: list, options: dict
    ):
        """Command handler implementation - not used in managed mode.

        The Fleet provides the command handler via set_command_handler().
        """
        pass

    async def _connect(self) -> None:
        """Connect to external services - not used in managed mode.

        The Fleet handles connection logic.
        """
        pass

    async def _disconnect(self) -> None:
        """Disconnect from external services - not used in managed mode.

        The Fleet handles disconnection logic.
        """
        pass

    async def _execution_loop(self) -> None:
        """Execution loop - not used in managed mode.

        The Fleet provides the execution loop logic.
        """
        pass
