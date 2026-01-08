#!/usr/bin/env python

# Copyright 2024 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Standard
import os
import logging
from pathlib import Path
import tempfile
import warnings
import asyncio
import threading
import traceback
from abc import ABC, abstractmethod
from typing import Coroutine

# Python 3.12+ compatibility for override decorator
try:
    from typing import override
except ImportError:
    from typing_extensions import override

# Python 3.13+ compatibility for deprecated decorator
try:
    from warnings import deprecated
except ImportError:
    from typing_extensions import deprecated

# Third Party
from inorbit_edge.models import RobotSessionModel
from inorbit_edge.robot import RobotSession, RobotSessionPool, RobotSessionFactory
from inorbit_edge.video import OpenCVCamera

# Optional dependency for connector system stats
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

# InOrbit
from inorbit_connector.commands import (  # noqa: F401
    # Re-export command-related functionality for backwards compatibility
    # TODO: Remove in the next major release
    CommandFailure,
    CommandResultCode,
    parse_custom_command_args,
)
from inorbit_connector.logging.logger import setup_logger
from inorbit_connector.models import (
    ConnectorConfig,
    InorbitConnectorConfig,
    MapConfig,
    MapConfigTemp,
    RobotConfig,
)


class FleetConnector(ABC):
    """Generic InOrbit fleet connector.

    This is the base class of an InOrbit fleet connector. Subclasses should implement
    all abstract methods.

    A lot of initialization logic is customizable through the configuration object.
    See self.__init__() for more details.
    """

    def __init__(self, config: ConnectorConfig, **kwargs) -> None:
        """Initialize the base connector with common functionality.

        Args:
            config (ConnectorConfig): The connector configuration

        Keyword Args:
            register_user_scripts (bool): Register user scripts automatically.
                Default is False
            default_user_scripts_dir (str): The default user scripts directory path to
                use if not explicitly set in the config.
                Default is
                    "~/.inorbit_connectors/connector-{self.__class__.__name__}/local/"
            create_user_scripts_dir (bool): The path to the user scripts directory.
                Relevant only if register_user_scripts is True.
                Default is False
            register_custom_command_handler (bool): Register custom command handler.
                Default is True
            publish_connector_system_stats (bool): When True, publish the connector
                host's system stats (CPU, RAM, HDD) as default values in cases where the
                implementation doesn't provide their own stats.
                Requires psutil to be installed with
                    `pip install inorbit-connector[system-stats]`.
                Default is False (zeroed defaults)
        """

        # Common information
        self.config = config
        # Cache of robot IDs in config.fleet. Accessed through the robot_ids property
        # Updated by update_fleet()
        self.__robot_ids: list[str] = []
        # update_fleet() may be called during user-defined implementation of _connect()
        # to update the fleet before initializing the robot sessions
        # Initialize the robot_ids cache
        self.update_fleet(config.fleet)

        # Per robot state
        self.__last_published_frame_ids: dict[str, str] = {}
        # Store system stats per robot until end of the execution loop
        self.__pending_system_stats: dict[str, dict] = {}
        # Track pending map fetches to avoid duplicate requests
        self.__pending_map_fetches: set[str] = set()
        self.__pending_map_fetches_lock = threading.Lock()
        # Managed temp directory for fetched map files (lazily initialized)
        self.__temp_map_dir: tempfile.TemporaryDirectory | None = None

        # Private dictionary for fast internal access (use self._get_session(robot_id)
        # for thread-safe access) in tight loops. It should not be accessed directly
        # by subclasses to maintain thread-safety
        self.__robot_sessions: dict[str, RobotSession] = {}

        # Threading for the main run methods
        # The connector runs an asycio loop within a spawned thread
        # self.__loop is initialized within __run_connector(), and only referenced
        # outside of it by the commands handler
        self.__stop_event = asyncio.Event()
        self.__thread = threading.Thread(target=self.__run_loop)
        self.__loop: asyncio.AbstractEventLoop | None = None

        # Additional initalization arguments
        self.__register_user_scripts = kwargs.get("register_user_scripts", False)
        self.__default_user_scripts_dir = kwargs.get(
            "default_user_scripts_dir",
            f"~/.inorbit_connectors/connector-{self.__class__.__name__}/local/",
        )
        self.__create_user_scripts_dir = kwargs.get("create_user_scripts_dir", False)
        self.__register_custom_command_handler = kwargs.get(
            "register_custom_command_handler", True
        )

        # Logging information
        setup_logger(config.logging)
        self._logger = logging.getLogger(__name__)

        # System stats default behavior
        self.__publish_connector_system_stats = kwargs.get(
            "publish_connector_system_stats", False
        )
        if self.__publish_connector_system_stats and not PSUTIL_AVAILABLE:
            self._logger.warning(
                "publish_connector_system_stats requires psutil. "
                "Install with: pip install inorbit-connector[system-stats]. "
                "Falling back to zeroed defaults."
            )
            self.__publish_connector_system_stats = False

        # Set up environment variables
        for env_var_name, env_var_value in config.env_vars.items():
            self._logger.info(f"Setting environment variable '{env_var_name}'")
            os.environ[env_var_name] = env_var_value

        # Create RobotSessionFactory with common configuration
        # HACK: Using RobotSessionModel preserves backwards compatibility with
        # automatically loaded environment variables Robot-specific values (robot_id,
        # robot_name) have to be ommited after initalization before passing the config
        # to the factory.
        robot_session_config = RobotSessionModel(
            api_key=config.api_key,
            endpoint=config.api_url,
            account_id=config.account_id,
            robot_key=config.inorbit_robot_key,
            robot_id="required_value",
            robot_name="required_value",
        )
        factory_kwargs = robot_session_config.model_dump(
            exclude={"robot_id", "robot_name"}
        )
        self.__session_factory = RobotSessionFactory(**factory_kwargs)

        # Create RobotSessionPool
        self.__session_pool = RobotSessionPool(self.__session_factory)

    @property
    def robot_ids(self) -> list[str]:
        """Get the list of robot IDs in the fleet."""
        # Return the cached list of robot IDs
        return self.__robot_ids

    def update_fleet(self, fleet: list[RobotConfig]) -> None:
        """Update the robot fleet.

        This method may be called during the user-defined implementation of _connect()
        to update the fleet configuration before initializing the robot sessions.
        e.g. fetching the robot list from a fleet manager API.

        Args:
            fleet (list[RobotConfig]): The new fleet configuration
        """
        # Update the fleet configuration
        self.config.fleet = fleet
        # Update robot ID cache
        self.__robot_ids = [robot.robot_id for robot in self.config.fleet]

    def _handle_command_exception(
        self,
        exception: Exception,
        command_name: str,
        robot_id: str,
        args: list,
        options: dict,
    ) -> None:
        """Handle exceptions raised during command execution.

        Args:
            exception: The exception that was raised
            command_name: Name of the command that failed
            robot_id: ID of the robot
            args: Command arguments
            options: Command options containing result_function
        """
        self._logger.error(
            f"Failed to execute command '{command_name}' for robot "
            f"{robot_id} with args {args}. "
            f"Exception:\n{str(exception) or exception.__class__.__name__}"
        )
        # If the exception was intentionally raised by the connector to indicate a
        # failure, pass the data to the result function and set the code to FAILURE
        if isinstance(exception, CommandFailure):
            options["result_function"](
                CommandResultCode.FAILURE,
                execution_status_details=exception.execution_status_details,
                stderr=exception.stderr,
            )
        # otherwise report a generic error and attach the exception message to stderr
        else:
            options["result_function"](
                CommandResultCode.FAILURE,
                execution_status_details="An error occurred executing custom command",
                stderr=str(exception) or exception.__class__.__name__,
            )

    def __register_custom_command_handler_for_session(
        self, session: RobotSession, async_handler: Coroutine
    ) -> None:
        """Register an async custom command handler wrapped in error handling logic.

        Args:
            session (RobotSession): The robot session to register the command handler
            for.
            async_handler (Coroutine): The custom commands handler.
        """

        def handler_wrapper(command_name: str, args: list, options: dict):
            try:
                # Handle the commands in the existing event loop and wait for the result
                asyncio.run_coroutine_threadsafe(
                    async_handler(session.robot_id, command_name, args, options),
                    self.__loop,
                ).result()
            except Exception as e:
                self._handle_command_exception(
                    e, command_name, session.robot_id, args, options
                )

        session.register_command_callback(handler_wrapper)

    def __register_user_scripts_for_session(
        self, session: RobotSession, path: str, create: bool = False
    ) -> None:
        """Register user scripts folder.

        Args:
            session (RobotSession): The robot session to register the user scripts for.
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
            session.register_commands_path(path, exec_name_regex=r".*\.sh")

    def __initialize_session(self, robot_id: str) -> RobotSession:
        """Initialize a robot session."""

        # The InOrbit hostname of the robot is set to the robot_id by default
        # There is no support for setting the display name of a robot through the
        # edge-sdk yet
        session = self.__session_pool.get_session(robot_id, robot_name=robot_id)

        # If enabled, register user scripts
        if self.__register_user_scripts:
            path = self.config.user_scripts_dir or os.path.expanduser(
                self.__default_user_scripts_dir
            )
            self.__register_user_scripts_for_session(
                session, path, self.__create_user_scripts_dir
            )

        # Set online status callback for EdgeSDK
        session.set_online_status_callback(
            lambda: self._is_fleet_robot_online(robot_id)
        )

        # If enabled, register the provided custom commands handler
        if self.__register_custom_command_handler:
            self.__register_custom_command_handler_for_session(
                session, self._inorbit_robot_command_handler
            )

        return session

    def __initialize_sessions(self) -> None:
        """Initialize the robot sessions."""

        for robot_id in self.robot_ids:
            self.__robot_sessions[robot_id] = self.__initialize_session(robot_id)
        self._logger.info(
            f"Initialized {len(self.__robot_sessions)} robot sessions for robots "
            f"{', '.join(self.robot_ids)}"
        )

    async def __connect(self) -> None:
        """Initialize the connection to InOrbit based on the provided configuration,
        and connect to external services calling self._connect().

        self.update_fleet() may be called during this method to update the fleet
        configuration before initializing the robot sessions.

        Raises:
            Exception: If the robot session cannot connect.
        """
        # Call the user-implemented connection logic
        await self._connect()

        # Connect to InOrbit
        self.__initialize_sessions()

    async def __disconnect(self) -> None:
        """Disconnect external services and disconnect from InOrbit."""

        # Disconnect from InOrbit
        for session in self.__robot_sessions.values():
            session.disconnect()

        # Clean up temporary map files
        if self.__temp_map_dir is not None:
            self.__temp_map_dir.cleanup()
            self.__temp_map_dir = None

        # Call the user-implemented disconnection logic
        await self._disconnect()

    def __run_connector(self) -> None:
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
        for robot_config in self.config.fleet:
            for idx, camera_config in enumerate(robot_config.cameras):
                self._logger.info(
                    f"Registering camera {idx} for robot {robot_config.robot_id}: "
                    f"{str(camera_config.video_url)}"
                )
                # If values are None, remove the key from the dictionary to use
                # edge-sdk defaults
                dump = camera_config.model_dump()
                clean = {k: v for k, v in dump.items() if v is not None}
                self.__robot_sessions[robot_config.robot_id].register_camera(
                    str(idx), OpenCVCamera(**clean)
                )

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
                # Publish stored system stats or defaults for all robots
                self.__publish_pending_system_stats()
            except Exception as e:
                self._logger.error(f"Error in execution loop: {e}")
                self._logger.error(f"Traceback: {traceback.format_exc()}")
                self.__pending_system_stats.clear()
                # Continue execution after a brief pause to avoid tight error loops
                await asyncio.sleep(1.0)

    def _get_robot_session(self, robot_id: str) -> RobotSession:
        """Get a robot session for a specific robot ID.

        Usually the connector API is enough to abstract from the edge-sdk, but in some
        cases accessing the robot session directly may be necessary.

        This method provides thread-safe access to robot sessions through the session
        pool.

        Args:
            robot_id (str): The robot ID to get the session for

        Returns:
            RobotSession: The robot session for the specified robot

        Raises:
            KeyError: If the robot_id is not found in the pool
        """
        return self.__session_pool.get_session(robot_id)

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

    def publish_robot_pose(
        self,
        robot_id: str,
        x: float,
        y: float,
        yaw: float,
        frame_id: str = None,
        **kwargs,
    ) -> None:
        """Publish a pose for a specific robot to InOrbit.
        If the frame_id has changed from the last published, the map will be updated.

        Args:
            robot_id (str): The robot ID to publish pose for
            x (float): X coordinate
            y (float): Y coordinate
            yaw (float): Yaw angle
            frame_id (str): Frame ID for the pose
            **kwargs: Additional arguments for pose publishing
        """
        session = self._get_robot_session(robot_id)
        last_published_frame_id = self.__last_published_frame_ids.get(robot_id, None)
        if frame_id != last_published_frame_id:
            self._logger.info(
                f"Updating map {frame_id} with new pose for robot {robot_id}."
            )
            self.publish_robot_map(robot_id, frame_id, is_update=True)
        session.publish_pose(x, y, yaw, frame_id, **kwargs)

    def publish_robot_map(
        self, robot_id: str, frame_id: str, is_update: bool = False
    ) -> None:
        """Publish the map metadata for a specific robot to InOrbit.

        If the map is not found in the current configuration, an async fetch will be
        scheduled to retrieve the map from the robot. Once fetched, the map will be
        published automatically.

        Args:
            robot_id (str): The robot ID to publish map for
            frame_id (str): The frame ID of the map
            is_update (bool): Whether this is an update to an existing map
        """
        session = self._get_robot_session(robot_id)
        if map_config := self.config.maps.get(frame_id):
            session.publish_map(
                file=map_config.file,
                map_id=map_config.map_id,
                map_label=map_config.map_label,
                frame_id=frame_id,
                x=map_config.origin_x,
                y=map_config.origin_y,
                resolution=map_config.resolution,
                ts=None,
                is_update=is_update,
                format_version=map_config.format_version,
            )
            self.__last_published_frame_ids[robot_id] = frame_id
        else:
            # Map not in config - schedule async fetch if not already pending
            self._schedule_map_fetch(robot_id, frame_id, is_update)

    def _get_temp_map_dir(self) -> Path:
        """Get the temporary directory for storing fetched map files.

        The directory is lazily created on first access and will be automatically
        cleaned up when the connector disconnects.

        Returns:
            Path: Path to the temporary map directory
        """
        if self.__temp_map_dir is None:
            self.__temp_map_dir = tempfile.TemporaryDirectory(
                prefix="inorbit-connector-maps-"
            )
        return Path(self.__temp_map_dir.name)

    def _schedule_map_fetch(
        self, robot_id: str, frame_id: str, is_update: bool
    ) -> None:
        """Schedule an async map fetch on the connector's event loop.

        This method is thread-safe. If a fetch for this frame_id is already in
        progress, the request will be ignored to avoid duplicates.

        Args:
            robot_id (str): The robot ID to fetch map for
            frame_id (str): The frame ID of the map to fetch
            is_update (bool): Whether this is an update to an existing map
        """
        if self.__loop is None or not self.__loop.is_running():
            self._logger.warning(
                f"Cannot fetch map {frame_id}: event loop not available"
            )
            return

        # Ensure atomic check-and-add for pending fetches
        with self.__pending_map_fetches_lock:
            if frame_id in self.__pending_map_fetches:
                self._logger.debug(f"Map fetch for {frame_id} already in progress")
                return
            self.__pending_map_fetches.add(frame_id)

        self._logger.info(
            f"Map {frame_id} not in configuration, scheduling async fetch"
        )

        asyncio.run_coroutine_threadsafe(
            self._fetch_and_publish_map(robot_id, frame_id, is_update),
            self.__loop,
        )

    async def _fetch_and_publish_map(
        self, robot_id: str, frame_id: str, is_update: bool
    ) -> None:
        """Async task to fetch a map and publish it once available.

        Args:
            robot_id (str): The robot ID to fetch map for
            frame_id (str): The frame ID of the map to fetch
            is_update (bool): Whether this is an update to an existing map
        """
        try:
            map_config = await self.fetch_robot_map(robot_id, frame_id)
            if map_config is None:
                self._logger.info(
                    f"Map {frame_id} could not be fetched from robot {robot_id}"
                )
                return

            # Write map image to managed temp directory
            temp_dir = self._get_temp_map_dir()
            temp_path = temp_dir / f"{frame_id}.png"
            temp_path.write_bytes(map_config.image)
            self._logger.debug(f"Created temporary map file: {temp_path}")

            # Create a new map configuration
            self.config.maps[frame_id] = MapConfig(
                file=temp_path,
                **map_config.model_dump(exclude={"image", "file"}),
            )
            self._logger.debug(f"Added map {frame_id} to configuration")

            # Now that the map is in config, publish it synchronously
            self.publish_robot_map(robot_id, frame_id, is_update)
        except Exception as e:
            self._logger.error(f"Failed to fetch map {frame_id}: {e}")
        finally:
            with self.__pending_map_fetches_lock:
                self.__pending_map_fetches.discard(frame_id)

    async def fetch_robot_map(
        self, robot_id: str, frame_id: str
    ) -> MapConfigTemp | None:
        """Fetch the map configuration for a specific robot and frame ID.

        Override this method in subclasses to implement map fetching from the robot
        or fleet management system.

        Args:
            robot_id (str): The robot ID to fetch the map for
            frame_id (str): The frame ID of the map to fetch

        Returns:
            MapConfigTemp | None: The map configuration with image bytes, or None
                if the map could not be fetched.
        """
        return None

    def publish_robot_odometry(self, robot_id: str, **kwargs) -> None:
        """Publish odometry for a specific robot to InOrbit.

        Args:
            robot_id (str): The robot ID to publish odometry for
            **kwargs: Odometry data
        """
        session = self._get_robot_session(robot_id)
        session.publish_odometry(**kwargs)

    def publish_robot_key_values(self, robot_id: str, **kwargs) -> None:
        """Publish key values for a specific robot to InOrbit.

        Args:
            robot_id (str): The robot ID to publish key values for
            **kwargs: Key-value data
        """
        session = self._get_robot_session(robot_id)
        session.publish_key_values(kwargs)

    def publish_robot_system_stats(self, robot_id: str, **kwargs) -> None:
        """Store system stats for a specific robot to be published at the end of the
        execution loop.

        System stats are stored and published after the execution loop completes. If no
        stats are stored for a robot, default zeroed values are published instead.

        Note:
            If immediate publishing is required, use `_get_robot_session(robot_id)` to
            access the underlying RobotSession and call `publish_system_stats()`
            directly.

        Args:
            robot_id (str): The robot ID to store system stats for
            **kwargs: System stats data (cpu_load_percentage, ram_usage_percentage,
                hdd_usage_percentage, ts)
        """
        self.__pending_system_stats[robot_id] = kwargs

    def __get_connector_system_stats(self) -> dict:
        """Get system stats from the connector's host environment.

        Returns:
            dict: System stats with cpu_load_percentage, ram_usage_percentage,
                and hdd_usage_percentage as floats between 0.0 and 1.0.
        """
        return {
            "cpu_load_percentage": psutil.cpu_percent() / 100.0,
            "ram_usage_percentage": psutil.virtual_memory().percent / 100.0,
            "hdd_usage_percentage": psutil.disk_usage("/").percent / 100.0,
        }

    def __publish_pending_system_stats(self) -> None:
        """Publish stored system stats for all robots, or defaults if none stored.

        This method is called automatically at the end of each execution loop iteration.
        For each robot in the fleet:
        - If system stats were stored via publish_robot_system_stats(), those are
        published
        - Otherwise, default values are published (connector host stats if
          publish_connector_system_stats is enabled, zeroed values otherwise).

        The reason publishing system stats is deferred is to ensure at least one system
        stats message is published for each robot, even if the connector does not
        explicitly provide values. This ensures stability of the online status of the
        robot in the UI, as it forces state requests if the robot was to appear offline.
        """
        default_values = (
            self.__get_connector_system_stats()
            if self.__publish_connector_system_stats
            else {
                "cpu_load_percentage": 0.0,
                "ram_usage_percentage": 0.0,
                "hdd_usage_percentage": 0.0,
            }
        )

        for robot_id in self.robot_ids:
            session = self._get_robot_session(robot_id)
            if pending_status := self.__pending_system_stats.get(robot_id):
                session.publish_system_stats(**pending_status)
            else:
                session.publish_system_stats(**default_values)

        # Clear stored stats for next iteration
        self.__pending_system_stats.clear()

    # Methods meant to be extended by subclasses
    @abstractmethod
    async def _connect(self) -> None:
        """Connect to any external services.

        This method should not be called directly. Instead, call the start() method to
        start the connector. This ensures that the connector is only started once.

        self.update_fleet() may be called during this method to update the fleet
        configuration before initializing the robot sessions.
        """
        ...

    @abstractmethod
    async def _disconnect(self) -> None:
        """Disconnect from any external services.

        This method should not be called directly. Instead, call the stop() method to
        stop the connector. This ensures that the connector is only stopped once.
        """
        ...

    @abstractmethod
    async def _execution_loop(self) -> None:
        """The main execution loop for the connector.

        This method should be overridden by subclasses to provide the execution loop for
        the connector, will be called repeatedly until the connector is stopped, and
        should not be called directly. Instead, call the start() or stop() methods to
        start or stop the connector. This ensures that the connector is only started or
        stopped once.
        """
        ...

    @abstractmethod
    async def _inorbit_robot_command_handler(
        self, robot_id: str, command_name: str, args: list, options: dict
    ) -> None:
        """Callback method for command messages for a specific robot.

        This method is called when a command is received from InOrbit for a specific
        robot.
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

        Args:
            robot_id (str): The robot ID that received the command
            command_name (str): The name of the command
            args (list): The list of arguments
            options (dict): The dictionary of options.
                It contains the `result_function` explained above.
        """
        ...

    def _is_fleet_robot_online(self, robot_id: str) -> bool:
        """Check if a specific robot is online.

        Default implementation assumes robot is online if connector is running.
        Override this method in specific connectors to provide robot-specific
        health checks (e.g., API connectivity, robot state, etc.).

        Args:
            robot_id (str): The robot ID to check

        Returns:
            bool: True if robot is online, False otherwise.
        """
        return True  # Base assumption: if connector is running, robot is online


class Connector(FleetConnector, ABC):
    """Generic InOrbit connector.

    This is the base class of an InOrbit connector. Subclasses should implement all
    abstract methods.

    It is a subclass of FleetConnector, but managing a single robot.

    A lot of initialization logic is customizable through the configuration object. See
    FleetConnector.__init__() for more details.
    """

    def __init__(self, robot_id: str, config: ConnectorConfig, **kwargs) -> None:
        """Initialize a new InOrbit connector.

        This class handles bidirectional communication with InOrbit.

        Args:
            robot_id (str): The ID of the InOrbit robot
            config (ConnectorConfig): The connector configuration.
                - New API: pass `ConnectorConfig` with a `fleet` field containing
                  multiple robot configurations. The one for the current robot will be
                  selected by the `robot_id` parameter.
                - Deprecated: pass `InorbitConnectorConfig` (single-robot); it will be
                  converted to a `ConnectorConfig`.

        Keyword Args:
            register_user_scripts (bool): Register user scripts automatically.
                Default False
            default_user_scripts_dir (str): Default user scripts directory path to use
                if not explicitly set in the config. Default is
                "~/.inorbit_connectors/connector-{robot_id}/local/"
            create_user_scripts_dir (bool): Whether to create the user scripts
                directory. Default False
                Relevant only if register_user_scripts is True.
        """
        self.robot_id = robot_id

        if isinstance(config, InorbitConnectorConfig):
            # Deprecated behavior
            warnings.warn(
                "Passing InorbitConnectorConfig to Connector.__init__ is deprecated; "
                "pass ConnectorConfig instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            fleet_config = config.to_fleet_config(robot_id)
        else:
            fleet_config = config.to_singular_config(robot_id)

        super().__init__(fleet_config, **kwargs)

    def _get_session(self) -> RobotSession:
        """Get the edge-sdk robot session for the current robot.

        Usually the connector API is enough to abstract from the edge-sdk, but in some
        cases accessing the robot session directly may be necessary.
        """
        return super()._get_robot_session(self.robot_id)

    @property
    @deprecated("Use self._get_session() instead")
    def _robot_session(self) -> RobotSession:
        return self._get_session()

    def _is_robot_online(self) -> bool:
        """Check if the robot is online.

        Default implementation assumes robot is online if connector is running.
        Override this method in specific connectors to provide robot-specific
        health checks (e.g., API connectivity, robot state, etc.).

        Returns:
            bool: True if robot is online, False otherwise.
        """
        return True  # Base assumption: if connector is running, robot is online

    @override
    def _is_fleet_robot_online(self, robot_id: str) -> bool:
        return self._is_robot_online()

    async def fetch_map(self, frame_id: str) -> MapConfigTemp | None:
        """Fetch the map configuration for a specific robot and frame ID.

        Override this method in subclasses to implement map fetching from the current
        robot.

        Args:
            frame_id (str): The frame ID of the map to fetch

        Returns:
            MapConfigTemp | None: The map configuration with image bytes, or None
                if the map could not be fetched.
        """
        return None

    @override
    async def fetch_robot_map(
        self, robot_id: str, frame_id: str
    ) -> MapConfigTemp | None:
        """
        Convenience override of the fetch_robot_map method to use a method of
        single-robot type.
        """
        return await self.fetch_map(frame_id)

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
            raise CommandFailure(
                execution_status_details="Oops!",
                stderr="XYZ happened"
            )

        Notice the use of the CommandFailure exception to intentionally indicate a
        failure. Other exceptions will be handled too, but the messages displayed in the
        UI will be generic.
        See the CommandFailure class for more details.

        Args:
            command_name (str): The name of the command
            args (list): The list of arguments
            options (dict): The dictionary of options.
                It contains the `result_function` explained above.
        """
        pass

    @override
    async def _inorbit_robot_command_handler(
        self, robot_id: str, command_name: str, args: list, options: dict
    ) -> None:
        await self._inorbit_command_handler(command_name, args, options)

    def publish_map(self, frame_id: str, is_update: bool = False) -> None:
        """Publish the map metadata to InOrbit. If `frame_id` is not found in the maps
        configuration, this method will not publish anything.
        """
        super().publish_robot_map(self.robot_id, frame_id, is_update)

    def publish_pose(
        self, x: float, y: float, yaw: float, frame_id: str, *args, **kwargs
    ) -> None:
        """Publish a pose to InOrbit. If the frame_id is different from the last
        published, it calls self.publish_map() to update the map.
        """
        super().publish_robot_pose(self.robot_id, x, y, yaw, frame_id, *args, **kwargs)

    def publish_odometry(self, **kwargs) -> None:
        """Publish odometry for a specific robot to InOrbit.

        Args:
            **kwargs: Odometry data
        """
        super().publish_robot_odometry(self.robot_id, **kwargs)

    def publish_key_values(self, **kwargs) -> None:
        """Publish key values for a specific robot to InOrbit.

        Args:
            **kwargs: Key-value data
        """
        super().publish_robot_key_values(self.robot_id, **kwargs)

    def publish_system_stats(self, **kwargs) -> None:
        """Store system stats to be published at the end of the execution loop.

        System stats are stored and published after the execution loop completes. If no
        stats are stored, default zeroed values are published instead.

        Note:
            If immediate publishing is required, use `_get_session()` to access the
            underlying RobotSession and call `publish_system_stats()` directly.

        Args:
            **kwargs: System stats data (cpu_load_percentage, ram_usage_percentage,
                hdd_usage_percentage, ts)
        """
        super().publish_robot_system_stats(self.robot_id, **kwargs)
