#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
from enum import Enum
import os
import logging
import asyncio
import threading
import traceback
from typing import Coroutine
from abc import ABC, abstractmethod

# Third Party
from inorbit_edge.models import RobotSessionModel
from inorbit_edge.robot import RobotSession
from inorbit_edge.video import OpenCVCamera

# InOrbit
from inorbit_connector.logging.logger import setup_logger
from inorbit_connector.models import InorbitConnectorConfig


class CommandResultCode(str, Enum):
    """The result code of a command execution."""

    SUCCESS = "0"
    FAILURE = "1"


class Connector(ABC):
    """Generic InOrbit connector.

    This is the base class of an InOrbit connector. Subclasses should implement all
    abstract methods.

    A lot of initialization logic is customizable through the configuration object. See
    self.__init__() for more details.
    """

    def __init__(self, robot_id: str, config: InorbitConnectorConfig, **kwargs) -> None:
        """Initialize a new InOrbit connector.

        This class handles bidirectional communication with InOrbit.

        Args:
            robot_id (str): The ID of the InOrbit robot
            config (InorbitConnectorConfig): The connector configuration

        Keyword Args:
            register_user_scripts (bool): Register user scripts automatically.
                Default is False
            default_user_scripts_dir (str): The default user scripts directory path to
                use if not explicitly set in the config.
                Default is "~/.inorbit_connectors/connector-{robot_id}/local/"
            create_user_scripts_dir (bool): The path to the user scripts directory.
                Relevant only if register_user_scripts is True.
                Default is False
        """

        # Common information
        self.robot_id = robot_id
        self.config = config
        self._last_published_frame_id = None

        # Threading for the main run methods
        # The connector runs an asycio loop within a spawned thread
        # self.__loop is initialized within __run_connector(), and only referenced
        # outside of it by the commands handler
        self.__stop_event = asyncio.Event()
        self.__thread = threading.Thread(target=self.__run_loop)
        self.__loop: asyncio.AbstractEventLoop | None = None

        # Logging information
        setup_logger(config.logging)
        self._logger = logging.getLogger(__name__)

        # Set up environment variables
        for env_var_name, env_var_value in config.env_vars.items():
            self._logger.info(f"Setting environment variable '{env_var_name}'")
            os.environ[env_var_name] = env_var_value

        # Create the robot session in InOrbit
        robot_session_config = RobotSessionModel(
            api_key=config.api_key,
            endpoint=config.api_url,
            account_id=config.account_id,
            robot_id=robot_id,
            robot_name=robot_id,
            robot_key=config.inorbit_robot_key,
        )
        self._robot_session = RobotSession(**robot_session_config.model_dump())

        # If enabled, register user scripts
        if kwargs.get("register_user_scripts", False):
            # Get user_scripts path
            path = config.user_scripts_dir
            if path is None:
                path = kwargs.get(
                    "default_user_scripts_dir",
                    f"~/.inorbit_connectors/connector-{robot_id}/local/",
                )
            user_scripts_path = os.path.expanduser(path)
            create_dir = kwargs.get("create_user_scripts_dir", False)
            self._register_user_scripts(user_scripts_path, create_dir)

        # If enabled, register the provided custom commands handler
        if kwargs.get("register_custom_command_handler", True):
            self._register_custom_command_handler(self._inorbit_command_handler)

    def _register_user_scripts(self, path: str, create: bool) -> None:
        """Register user scripts folder.

        Args:
            path (str): The path to the user scripts directory.
            create (bool): Create the directory if it doesn't exist.
        """
        if not os.path.exists(path):
            if create:
                self._logger.info(f"Creating user_scripts directory: {path}")
                os.makedirs(path, exist_ok=True)
            else:
                self._logger.warning(f"User_scripts directory not found: {path}")
                return
        if os.path.exists(path):
            self._logger.info(f"Registering user_scripts path: {path}")
            # NOTE: this only supports bash execution (exec_name_regex is set to
            # files with '.sh' extension).
            # More script types can be supported, but right now is only limited to
            # bash scripts
            self._robot_session.register_commands_path(path, exec_name_regex=r".*\.sh")

    def _register_custom_command_handler(self, async_handler: Coroutine) -> None:
        """Register an async custom command handler wrapped in error handling logic.

        Args:
            async_handler (Coroutine): The custom commands handler.
        """

        def handler_wrapper(command_name: str, args: list, options: dict):
            try:
                # Handle the commands in the existing event loop and wait for the result
                asyncio.run_coroutine_threadsafe(
                    async_handler(command_name, args, options), self.__loop
                ).result()
            except Exception as e:
                self._logger.error(
                    f"Failed to execute command '{command_name}' with args {args}. "
                    f"Exception:\n{str(e) or e.__class__.__name__}"
                )
                options["result_function"](
                    CommandResultCode.FAILURE,
                    execution_status_details=(
                        "An error occured executing custom command"
                    ),
                    stderr=str(e) or e.__class__.__name__,
                )

        self._robot_session.register_command_callback(handler_wrapper)

    @abstractmethod
    async def _inorbit_command_handler(
        self, command_name: str, args: list, options: dict
    ):
        """Callback method for command messages. This method is called when a command
        is received from InOrbit.
        Will automatically be registered if `register_custom_command_handler`
        constructor keyword argument is set, which is the default behavior.

        The result function will always be included in the options dictionary and must
        be called in order to report the result of a command. It has the following
        signature:

        options['result_function'](
            result_code: CommandResultCode,
            execution_status_details: str | None = None,
            stdout: str | None = None,
            stderr: str | None = None,
        ) -> None

        e.g.:
        if success:
            return options['result_function'](CommandResultCode.SUCCESS)
        else:
            return options['result_function'](
                CommandResultCode.FAILURE,
                stderr="Example error"
            )

        Args:
            command_name (str): The name of the command
            args (list): The list of arguments
            options (dict): The dictionary of options.
                It contains the `result_function` explained above.
        """
        pass

    @abstractmethod
    async def _connect(self) -> None:
        """Connect to any external services.

        This method should not be called directly. Instead, call the start() method to
        start the connector. This ensures that the connector is only started once.
        """
        pass

    async def __connect(self) -> None:
        """Initialize the connection to InOrbit based on the provided configuration,
        and connect to external services calling self._connect().

        Raises:
            Exception: If the robot session cannot connect.
        """
        # Call the user-implemented connection logic
        await self._connect()

        # Connect to InOrbit
        self._robot_session.connect()

    @abstractmethod
    async def _disconnect(self) -> None:
        """Disconnect from any external services.

        This method should not be called directly. Instead, call the stop() method to
        stop the connector. This ensures that the connector is only stopped once.
        """
        pass

    async def __disconnect(self) -> None:
        """Disconnect external services and disconnect from InOrbit."""

        # Disconnect from InOrbit
        self._robot_session.disconnect()

        # Call the user-implemented disconnection logic
        await self._disconnect()

    @abstractmethod
    async def _execution_loop(self) -> None:
        """The main execution loop for the connector.

        This method should be overridden by subclasses to provide the execution loop for
        the connector, will be called repeatedly until the connector is stopped, and
        should not be called directly. Instead, call the start() or stop() methods to
        start or stop the connector. This ensures that the connector is only started or
        stopped once.
        """
        pass

    def publish_map(self, frame_id: str, is_update: bool = False) -> None:
        """Publish the map metadata to InOrbit. If `frame_id` is not found in the maps
        configuration, this method will not publish anything.
        """
        if map_config := self.config.maps.get(frame_id):
            self._robot_session.publish_map(
                file=map_config.file,
                map_id=map_config.map_id,
                frame_id=frame_id,
                x=map_config.origin_x,
                y=map_config.origin_y,
                resolution=map_config.resolution,
                ts=None,
                is_update=is_update,
            )
            self._last_published_frame_id = frame_id
        else:
            self._logger.error(
                f"Map {frame_id} not found in the current configuration."
                " Map message will not be sent."
            )

    def publish_pose(
        self, x: float, y: float, yaw: float, frame_id: str, *args, **kwargs
    ) -> None:
        """Publish a pose to InOrbit. If the frame_id is different from the last
        published, it calls self.publish_map() to update the map.
        """
        if frame_id != self._last_published_frame_id:
            self._logger.info(f"Updating map {frame_id} with new pose.")
            self.publish_map(frame_id, is_update=True)
        self._robot_session.publish_pose(x, y, yaw, frame_id, *args, **kwargs)

    def start(self) -> None:
        """Start the connector in a new thread.

        This method should be called to start the execution of this connector. It
        creates an event loop in a new thread and runs the connector in it.

        After calling start(), use join() to block until the connector is stopped.
        Use stop() to stop the connector.

        It:
        - calls self._connect() to connect to any external services.
        - sets up camera feeds defined in the configuration.
        - runs the execution loop in a new thread.
        - calls self._disconnect() to disconnect from any external services once the
          connector is stopped.
        """

        # Prevent starting an already running thread
        if not self.__thread.is_alive():
            self.__stop_event.clear()

            # Create and start the thread
            self.__thread = threading.Thread(target=self.__run_connector)
            self.__thread.start()

    def join(self) -> None:
        """Join the execution loop of this connector.

        This method should be called to join the execution loop of this connector and
        will block until it ends.
        """
        self.__thread.join()

    def stop(self) -> None:
        """Stop the execution loop of this connector.

        This method should be called to stop the execution loop of this connector, will
        block until the execution loop is stopped, and will call disconnect() to clean
        up any external connections.
        """

        # Stop the execution loop
        self._logger.info("Stopping connector")
        self.__stop_event.set()
        self.__thread.join(timeout=5)
        if self.__thread.is_alive():
            raise Exception("Thread did not stop in time")

    def __run_connector(self):
        """The target function of the connector's thread.

        It connects to InOrbit via the edge-sdk, start the execution loop and
        disconnects all services when the connector is signaled stop via self.stop().
        """

        # Create a new event loop for this thread
        self.__loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.__loop)

        # Connect to external services and create the InOrbit session
        self.__loop.run_until_complete(self.__connect())

        # Set up camera feeds
        for idx, camera_config in enumerate(self.config.cameras):
            self._logger.info(
                f"Registering camera {idx}: {str(camera_config.video_url)}"
            )
            # If values are None, use default instead
            dump = camera_config.model_dump()
            clean = {k: v for k, v in dump.items() if v is not None}
            self._robot_session.register_camera(str(idx), OpenCVCamera(**clean))

        try:
            self.__loop.run_until_complete(self.__run_loop())
        except Exception as e:
            self._logger.error(f"Error in execution loop: {e}")
            self._logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            self.__loop.run_until_complete(self.__disconnect())
            self.__loop.close()

    async def __run_loop(self) -> None:
        """The main coroutine of the connector.

        This coroutine will run the execution loop of the connector until the stop event
        is set.
        It uses self.config.update_freq to set a maximum frequency for the execution
        loop, but it will never run faster than the actual execution of the loop body.

        Exceptions raised by self._execution_loop() are caught and logged to prevent
        the connector from crashing. It is recommended to handle exceptions within the
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
