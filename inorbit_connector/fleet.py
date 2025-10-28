#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import asyncio
import logging
import os
import threading
import traceback
from abc import ABC, abstractmethod
from typing import Dict, List

# InOrbit
from inorbit_connector.logging.logger import setup_logger
from inorbit_connector.managed_connector import ManagedConnector
from inorbit_connector.models import InorbitConnectorConfig


class Fleet(ABC):
    """Abstract base class for managing a fleet of robots.

    This class manages multiple ManagedConnector instances, providing a single
    thread and event loop for all connectors. Subclasses must implement the
    fleet-level execution loop and command handling logic.

    The Fleet owns the lifecycle of all connectors, including connection,
    disconnection, and the main execution loop.
    """

    def __init__(
        self, robot_ids: List[str], config: InorbitConnectorConfig, **kwargs
    ) -> None:
        """Initialize the Fleet.

        Args:
            robot_ids (List[str]): List of robot IDs to manage
            config (InorbitConnectorConfig): The connector configuration (shared by all robots)

        Keyword Args:
            register_user_scripts (bool): Register user scripts automatically.
                Default is False
            default_user_scripts_dir (str): The default user scripts directory path to
                use if not explicitly set in the config.
                Default is "~/.inorbit_connectors/fleet-{robot_id}/local/"
            create_user_scripts_dir (bool): The path to the user scripts directory.
                Relevant only if register_user_scripts is True.
                Default is False
        """
        # Common information
        self.robot_ids = robot_ids
        self.config = config

        # Threading for the main run methods
        # The fleet runs an asyncio loop within a spawned thread
        # self.__loop is initialized within __run_fleet(), and only referenced
        # outside of it by the commands handler
        self.__stop_event: asyncio.Event | None = None
        self.__thread: threading.Thread | None = None
        self.__loop: asyncio.AbstractEventLoop | None = None

        # Logging information
        setup_logger(config.logging)
        self._logger = logging.getLogger(__name__)

        # Set up environment variables
        for env_var_name, env_var_value in config.env_vars.items():
            self._logger.info(f"Setting environment variable '{env_var_name}'")
            os.environ[env_var_name] = env_var_value

        # Create managed connectors for all robots
        self._connectors: Dict[str, ManagedConnector] = {}
        for robot_id in robot_ids:
            self._logger.info(f"Creating connector for robot '{robot_id}'")
            connector = ManagedConnector(robot_id, config, **kwargs)
            self._connectors[robot_id] = connector

            # Set up command handler for this connector
            connector.set_fleet_command_handler(self._fleet_command_handler)

    @abstractmethod
    async def _fleet_command_handler(
        self, robot_id: str, command_name: str, args: list, options: dict
    ) -> None:
        """Handle commands received from InOrbit for any robot in the fleet.

        This is the fleet-level command handler that receives commands for all
        robots. Subclasses must implement this method to handle commands.

        The result function must be called to report the result of the command:

        options['result_function'](
            result_code: CommandResultCode,
            execution_status_details: str | None = None,
            stdout: str | None = None,
            stderr: str | None = None,
        ) -> None

        Args:
            robot_id (str): The ID of the robot that received the command
            command_name (str): The name of the command
            args (list): The list of arguments
            options (dict): The dictionary of options, including 'result_function'
        """
        pass

    @abstractmethod
    async def _connect(self) -> None:
        """Connect to any external services needed by the fleet.

        This is called after all individual robots are connected to InOrbit.
        Subclasses should implement this method to connect to fleet-level services
        (e.g., a fleet management API, shared databases, etc.).

        This method should not be called directly. Instead, call the start() method to
        start the fleet. This ensures that the fleet is only started once.
        """
        pass

    async def __connect(self) -> None:
        """Initialize the connection to InOrbit for all robots and connect to
        external services calling self._connect().

        Raises:
            Exception: If any robot session cannot connect.
        """
        # Connect all robots to InOrbit (uses Connector's private __connect via name mangling)
        await asyncio.gather(
            *(
                connector._Connector__connect()
                for connector in self._connectors.values()
            ),
            return_exceptions=True,
        )

        # Call the user-implemented connection logic
        await self._connect()

    @abstractmethod
    async def _disconnect(self) -> None:
        """Disconnect from any external services.

        This is called before individual robots are disconnected from InOrbit.
        Subclasses should implement this method to disconnect from fleet-level
        services.

        This method should not be called directly. Instead, call the stop() method to
        stop the fleet. This ensures that the fleet is only stopped once.
        """
        pass

    async def __disconnect(self) -> None:
        """Disconnect external services and disconnect all robots from InOrbit."""

        # Call the user-implemented disconnection logic
        await self._disconnect()

        # Disconnect all robots from InOrbit (uses Connector's private __disconnect via name mangling)
        await asyncio.gather(
            *(
                connector._Connector__disconnect()
                for connector in self._connectors.values()
            ),
            return_exceptions=True,
        )

    @abstractmethod
    async def _execution_loop(self) -> None:
        """The main execution loop for the fleet.

        This method should be overridden by subclasses to provide the execution loop for
        the fleet, will be called repeatedly until the fleet is stopped, and
        should not be called directly. Instead, call the start() or stop() methods to
        start or stop the fleet. This ensures that the fleet is only started or
        stopped once.
        """
        pass

    def start(self) -> None:
        """Start the fleet in a new thread.

        This method should be called to start the execution of this fleet. It
        creates an event loop in a new thread and runs the fleet in it.

        After calling start(), use join() to block until the fleet is stopped.
        Use stop() to stop the fleet.

        It:
        - calls self._connect() to connect to any external services.
        - sets up camera feeds defined in the configuration for all robots.
        - runs the execution loop in a new thread.
        - calls self._disconnect() to disconnect from any external services once the
          fleet is stopped.
        """

        # Prevent starting an already running thread
        if self.__thread is None or not self.__thread.is_alive():
            # Create and start the thread
            self.__thread = threading.Thread(target=self.__run_fleet)
            self.__thread.start()

    def join(self) -> None:
        """Join the execution loop of this fleet.

        This method should be called to join the execution loop of this fleet and
        will block until it ends.
        """
        self.__thread.join()

    def stop(self) -> None:
        """Stop the execution loop of this fleet.

        This method should be called to stop the execution loop of this fleet, will
        block until the execution loop is stopped, and will call disconnect() to clean
        up any external connections.
        """

        # Stop the execution loop
        self._logger.info("Stopping fleet")
        if self.__stop_event:
            self.__stop_event.set()
        if self.__thread:
            self.__thread.join(timeout=5)
            if self.__thread.is_alive():
                raise Exception("Thread did not stop in time")

    def __run_fleet(self):
        """The target function of the fleet's thread.

        It connects to InOrbit via the edge-sdk, start the execution loop and
        disconnects all services when the fleet is signaled stop via self.stop().
        """

        # Create a new event loop for this thread
        self.__loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.__loop)

        # Create the stop event in the correct event loop context
        self.__stop_event = asyncio.Event()

        # Attach the event loop to all connectors
        for connector in self._connectors.values():
            connector.attach_loop(self.__loop)

        # Connect to external services and create the InOrbit sessions
        self.__loop.run_until_complete(self.__connect())

        # Set up camera feeds for all robots
        for robot_id, connector in self._connectors.items():
            self._logger.info(f"Registering cameras for robot '{robot_id}'")
            connector.register_cameras()

        try:
            self.__loop.run_until_complete(self.__run_loop())
        except Exception as e:
            self._logger.error(f"Error in execution loop: {e}")
            self._logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            self.__loop.run_until_complete(self.__disconnect())
            self.__loop.close()

    async def __run_loop(self) -> None:
        """The main coroutine of the fleet.

        This coroutine will run the execution loop of the fleet until the stop event
        is set.
        It uses self.config.update_freq to set a maximum frequency for the execution
        loop, but it will never run faster than the actual execution of the loop body.

        Exceptions raised by self._execution_loop() are caught and logged to prevent
        the fleet from crashing. It is recommended to handle exceptions within the
        loop and publish the errors.
        """
        while not self.__stop_event.is_set():
            try:
                await asyncio.gather(
                    self._execution_loop(),
                    asyncio.sleep(1.0 / self.config.update_freq),
                )
            except Exception as e:
                self._logger.error(f"Error in execution loop: {e}")
                self._logger.error(f"Traceback: {traceback.format_exc()}")
                # Continue execution after a brief pause to avoid tight error loops
                await asyncio.sleep(1.0)
