#!/usr/bin/env python

# Copyright 2024 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Standard
import os
import logging
import socket
from pathlib import Path
import tempfile
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

# Third Party
from inorbit_edge.models import RobotSessionModel
from inorbit_edge.robot import (
    RobotSession,
    RobotSessionPool,
    RobotSessionFactory,
)
from inorbit_edge.video import OpenCVCamera

# Optional dependency for connector system stats
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

# InOrbit
from inorbit_connector.commands import (
    CommandFailure,
    CommandResultCode,
)
from inorbit_connector.logging.logger import setup_logger
from inorbit_connector import metrics as _metrics
from inorbit_connector.metrics import (
    MetricsServer,
    register_framework_gauges,
    setup_prometheus_metrics,
)
from inorbit_connector.models import (
    ConnectorRootConfig,
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

    def __init__(self, config: ConnectorRootConfig, **kwargs) -> None:
        """Initialize the base connector with common functionality.

        Args:
            config (ConnectorRootConfig): The connector configuration

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

        # Per robot state
        self.__last_published_frame_ids: dict[str, str] = {}
        # Store system stats per robot until end of the execution loop
        self.__pending_system_stats: dict[str, dict] = {}
        # Track pending map fetches to avoid duplicate requests
        self.__pending_map_fetches: set[str] = set()
        self.__pending_map_fetches_lock = threading.Lock()
        # Managed temp directory for fetched map files (lazily initialized)
        self.__temp_map_dir: tempfile.TemporaryDirectory | None = None

        # Private dictionary for fast internal access (use self._get_robot_session(
        # robot_id) for thread-safe access) in tight loops. It should not be accessed
        # directly by subclasses to maintain thread-safety
        self.__robot_sessions: dict[str, RobotSession] = {}
        # Lock guarding fleet mutation: config.fleet, __robot_sessions membership, and
        # the per-robot state dicts (last-frame-id, pending system stats).
        self.__fleet_lock = threading.RLock()

        # Threading for the main run methods
        # The connector runs an asycio loop within a spawned thread
        # self.__loop is initialized within __run_connector(), and only referenced
        # outside of it by the commands handler
        self.__stop_event = asyncio.Event()
        self.__thread = threading.Thread(target=self.__run_loop)
        self.__loop: asyncio.AbstractEventLoop | None = None

        # Long-lived background tasks scheduled via _create_supervised_task /
        # _spawn_logged_task. Cancelled and awaited in __disconnect().
        self.__background_tasks: list[asyncio.Task] = []

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
            endpoint=config.connection_config_url,
            rest_api_endpoint=config.api_url,
            robot_key=config.inorbit_robot_key,
            robot_id="required_value",
            robot_name="required_value",
        )
        factory_kwargs = robot_session_config.model_dump(
            exclude={"robot_id", "robot_name"}
        )
        # Select MQTT transport. The edge-sdk's RobotSession accepts
        # ``use_websockets`` as a constructor kwarg and uses it to pick between
        # the "tcp" and "websockets" paho transports (with ``use_ssl`` still
        # controlling TLS, so True+True yields a wss:// connection).
        factory_kwargs["use_websockets"] = config.use_websockets
        self.__session_factory = RobotSessionFactory(**factory_kwargs)

        # Create RobotSessionPool
        self.__session_pool = RobotSessionPool(self.__session_factory)

        # --- Metrics subsystem (opt-in via config.metrics.enabled) --------
        self._connector_id = (
            config.metrics.connector_id or socket.gethostname() or "inorbit-connector"
        )
        metrics_active = setup_prometheus_metrics(
            config=config.metrics,
            connector_type=self._connector_type,
            connector_id=self._connector_id,
        )
        register_framework_gauges(
            is_alive=lambda: self.__thread.is_alive(),
            robot_ids=lambda: self.robot_ids,
            is_session_connected=self._is_session_connected,
        )
        self._metrics_server: MetricsServer | None = (
            MetricsServer(config=config.metrics, connector_id=self._connector_id)
            if metrics_active
            else None
        )

    @property
    def robot_ids(self) -> list[str]:
        """Get the list of robot IDs in the fleet."""
        # Return a copy of the fleet robotIds derived from config.fleet under the lock.
        with self.__fleet_lock:
            return [robot.robot_id for robot in self.config.fleet]

    @property
    def _connector_type(self) -> str:
        """Connector type identifier read from the ``CONNECTOR_TYPE`` class
        variable on the ``connector_config`` subclass.

        ``CONNECTOR_TYPE`` is the source of truth for the connector's identity.
        ``ConnectorRootConfig._check_connector_type_matches_class_var`` guarantees
        it equals ``config.connector_type``.
        """
        return type(self.config.connector_config).CONNECTOR_TYPE

    def update_fleet(self, fleet: list[RobotConfig]) -> None:
        """Update the robot fleet.

        This is the single entry point for fleet membership. It diffs the requested
        fleet against the currently active robot sessions and:

        - creates and connects a session for each newly added robot (registering its
          cameras, command handler and online-status callback), and
        - disconnects and frees the session of each robot no longer present, clearing
          its per-robot state.

        It is idempotent: robots already in the fleet are left untouched. It reconciles
        membership only. A robot present in both the old and new fleet keeps its
        existing session even if its ``RobotConfig`` changed. The connector's startup
        reconciles ``self.config.fleet`` to create the initial sessions, and subclasses
        may call this at runtime (from ``_connect()`` onward) to implement fleet runtime
        updates, e.g. fetching the robot list from a fleet manager API.

        Note:
            Sessions are created/destroyed immediately, so this must be called once the
            connector is connecting or running (i.e. from ``_connect()`` or the
            execution loop), not before ``start()``.

            A robot present in both the old and new fleet is treated as unchanged even
            if its ``RobotConfig`` differs (e.g. its cameras changed). To apply a
            changed config to a running robot, call ``remove_robot()`` then
            ``add_robot()``.

        Args:
            fleet (list[RobotConfig]): The new fleet configuration

        Raises:
            ValueError: If ``fleet`` contains duplicate robot IDs.
        """

        # TODO(b-Tomas): Session creation/teardown (MQTT connect/disconnect) runs while
        # holding the fleet lock, so a slow broker connection briefly blocks publishing
        # from other threads. Fleet mutations are expected to be infrequent, but
        # consider fixing this.

        self.__apply_fleet(fleet)

    def __apply_fleet(self, fleet: list[RobotConfig]) -> None:
        """Reconcile the live robot sessions to match ``fleet``.

        This is the implementation behind ``update_fleet()``. It is kept private so the
        connector's own startup (``__connect``) can reconcile the initial fleet even on
        the single-robot ``Connector`` subclass, which overrides the public
        ``update_fleet``/``add_robot``/``remove_robot`` to raise.
        """
        new_ids = [robot.robot_id for robot in fleet]
        if len(set(new_ids)) != len(new_ids):
            raise ValueError("Robot ids must be unique")

        # The whole reconcile runs under the lock so a fleet change is atomic with
        # respect to concurrent add_robot()/remove_robot()/update_fleet() calls. The
        # lock is re-entrant, so the wrappers can hold it across their read+delegate.
        with self.__fleet_lock:
            configs = {robot.robot_id: robot for robot in fleet}
            to_remove = [rid for rid in self.__robot_sessions if rid not in configs]
            to_add = [rid for rid in new_ids if rid not in self.__robot_sessions]

            # Create the new sessions before mutating any membership or state, so a
            # failure to connect rolls back cleanly and never leaves the fleet listing a
            # robot without a session.
            created: dict[str, RobotSession] = {}
            try:
                for robot_id in to_add:
                    created[robot_id] = self.__initialize_session(configs[robot_id])
            except Exception:
                # get_session() registers the session in the pool before connecting, so
                # free every attempted add (a no-op when the pool has none) to undo any
                # half-built session, then re-raise with membership untouched.
                for robot_id in to_add:
                    self.__session_pool.free_robot_session(robot_id)
                raise

            # Commit the membership and drop removed robots. Kept robots retain their
            # existing RobotConfig (their session is not re-created), so config.fleet
            # stays consistent with the live sessions; only newly added robots take
            # the incoming config. To apply a changed config to a running robot, call
            # remove_robot() then add_robot().
            old_by_id = {rc.robot_id: rc for rc in self.config.fleet}
            self.config.fleet = [
                rc if rc.robot_id in created else old_by_id.get(rc.robot_id, rc)
                for rc in fleet
            ]
            for robot_id in to_remove:
                self.__last_published_frame_ids.pop(robot_id, None)
                self.__pending_system_stats.pop(robot_id, None)
                self.__robot_sessions.pop(robot_id, None)
                # free_robot_session disconnects and removes the session from the
                # pool; no-op if the pool has no session for this robot.
                self.__session_pool.free_robot_session(robot_id)
            self.__robot_sessions.update(created)

    def add_robot(self, robot_config: RobotConfig) -> None:
        """Add a single robot to the fleet at runtime.

        Convenience wrapper over ``update_fleet()``: appends the robot to the current
        fleet and reconciles, which creates and connects its session (registering its
        cameras, command handler and online-status callback).

        Note:
            The session is created immediately, so call this once the connector is
            connecting or running (from ``_connect()`` onward), not before ``start()``.

        Args:
            robot_config (RobotConfig): The configuration of the robot to add.

        Raises:
            ValueError: If a robot with the same ``robot_id`` is already in the fleet.
        """
        with self.__fleet_lock:
            if any(r.robot_id == robot_config.robot_id for r in self.config.fleet):
                raise ValueError(
                    f"Robot '{robot_config.robot_id}' is already in the fleet"
                )
            self.__apply_fleet([*self.config.fleet, robot_config])

    def remove_robot(self, robot_id: str) -> None:
        """Remove a single robot from the fleet at runtime.

        Convenience wrapper over ``update_fleet()``: drops the robot from the current
        fleet and reconciles, which disconnects and frees its session and clears its
        per-robot state. Idempotent: removing a robot that is not in the fleet logs a
        warning and returns without error.

        Args:
            robot_id (str): The ID of the robot to remove.
        """
        with self.__fleet_lock:
            if not any(r.robot_id == robot_id for r in self.config.fleet):
                self._logger.warning(
                    f"remove_robot: robot '{robot_id}' is not in the fleet"
                )
                return
            self.__apply_fleet(
                [robot for robot in self.config.fleet if robot.robot_id != robot_id]
            )

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

    def __initialize_session(self, robot_config: RobotConfig) -> RobotSession:
        """Initialize a robot session for the given robot configuration."""

        robot_id = robot_config.robot_id
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

        # Register cameras declared in this robot's configuration.
        for idx, camera_config in enumerate(robot_config.cameras):
            self._logger.info(
                f"Registering camera {idx} for robot {robot_id}: "
                f"{str(camera_config.video_url)}"
            )
            # If values are None, remove the key from the dictionary to use
            # edge-sdk defaults
            dump = camera_config.model_dump()
            clean = {k: v for k, v in dump.items() if v is not None}
            session.register_camera(str(idx), OpenCVCamera(**clean))

        return session

    async def __connect(self) -> None:
        """Initialize the connection to InOrbit based on the provided configuration,
        and connect to external services calling self._connect().

        After self._connect() returns, the initial robot sessions are created via
        self.update_fleet(self.config.fleet). Subclasses may also populate the fleet
        themselves during self._connect() (via update_fleet() or add_robot()), in which
        case that final reconcile is a no-op.

        Raises:
            Exception: If the robot session cannot connect.
        """
        # Call the user-implemented connection logic
        await self._connect()

        # Create the InOrbit sessions for the current fleet. Calls the private reconcile
        # directly so it also works on the single-robot Connector subclass, which blocks
        # the public update_fleet().
        self.__apply_fleet(self.config.fleet)
        robot_ids = self.robot_ids
        self._logger.info(
            f"Initialized {len(robot_ids)} robot session(s)"
            + (f" for robots {', '.join(robot_ids)}" if robot_ids else "")
        )

    async def __disconnect(self) -> None:
        """Disconnect external services and disconnect from InOrbit."""

        # Stop supervised background tasks first so their loops stop touching
        # robot sessions before we tear those sessions down. Clear the list
        # up front so the done-callbacks' self-removal is a no-op.
        tasks = self.__background_tasks
        self.__background_tasks = []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Tear the fleet down while holding the lock so no robot can be added (via
        # add_robot/update_fleet from another thread) mid-teardown. Free each session
        # from the pool (not just disconnect it) so a subsequent start() rebuilds and
        # reconnects fresh sessions instead of reusing stale, disconnected ones.
        with self.__fleet_lock:
            for robot_id in list(self.__robot_sessions):
                self.__session_pool.free_robot_session(robot_id)
            self.__robot_sessions.clear()
            self.__last_published_frame_ids.clear()
            self.__pending_system_stats.clear()

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

        try:
            # Connect to external services and create the InOrbit sessions.
            self.__loop.run_until_complete(self.__connect())
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
                _metrics.execution_loop_ticks.add(1)
            except Exception as e:
                _metrics.execution_loop_errors.add(1)
                self._logger.error(f"Error in execution loop: {e}")
                self._logger.error(f"Traceback: {traceback.format_exc()}")
                with self.__fleet_lock:
                    self.__pending_system_stats.clear()
                # Continue execution after a brief pause to avoid tight error loops
                await asyncio.sleep(1.0)

    def _get_robot_session(self, robot_id: str) -> RobotSession | None:
        """Get the active robot session for a specific robot ID, or None.

        Usually the connector API is enough to abstract from the edge-sdk, but in some
        cases accessing the robot session directly may be necessary.

        This method provides thread-safe access to the connector's active robot
        sessions. It reads the connector's own session map rather than the pool, so it
        never creates a session for a robot that is not in the fleet, and returns None
        when the robot has no active session so the ``publish_*`` paths can skip it.

        Args:
            robot_id (str): The robot ID to get the session for

        Returns:
            RobotSession | None: The robot's active session, or None if it has none.
        """
        with self.__fleet_lock:
            return self.__robot_sessions.get(robot_id)

    def _is_session_connected(self, robot_id: str) -> bool:
        """Return True if the MQTT session for ``robot_id`` is currently connected.

        Used by the ``inorbit.connector.session.connected`` ObservableGauge to
        detect the case where the process is alive but its MQTT link to
        InOrbit has dropped. Reads the connector's own session dict rather
        than the pool to avoid any side effects (the pool's ``get_session``
        triggers a connect attempt on miss). Returns False when the session
        has not been initialized yet, which is the normal state before
        ``_connect()`` runs.
        """
        session = self._get_robot_session(robot_id)
        if session is None:
            return False
        try:
            return bool(session.client.is_connected())
        except Exception:
            return False

    def _create_supervised_task(
        self, name: str, coro_factory, restart_delay: float = 5.0
    ) -> asyncio.Task:
        """Schedule a long-lived background coroutine under supervision.

        Periodic work placed inside ``_execution_loop`` is already supervised by
        the framework (``__run_loop`` catches, logs and retries it). Work that
        needs a cadence other than ``config.update_freq`` (e.g. a fast pose loop
        and a slower key-value loop) must be scheduled here rather than via a
        bare ``asyncio.create_task``: a bare task that raises dies silently (its
        exception is stored on a task nobody awaits and is never logged), is
        never restarted, and freezes that datasource until the process restarts.

        This wraps ``coro_factory`` in a loop that, if the coroutine returns or
        raises, logs it (with traceback) and restarts it after ``restart_delay``
        seconds. ``CancelledError`` is propagated so the task stops cleanly on
        shutdown. The task is tracked and cancelled in teardown.

        Must be called from the connector's event loop (e.g. from ``_connect``).

        Args:
            name: Human-readable name used in log messages.
            coro_factory: Zero-arg callable returning a fresh coroutine; called
                again on each restart.
            restart_delay: Seconds to wait before restarting after exit/crash.

        Returns:
            The supervising ``asyncio.Task``.
        """
        task = asyncio.create_task(self.__supervise(name, coro_factory, restart_delay))
        task.add_done_callback(self.__log_task_exception)
        self.__background_tasks.append(task)
        return task

    async def __supervise(self, name, coro_factory, restart_delay) -> None:
        """Run ``coro_factory`` forever, logging+restarting it on exit/crash."""
        while True:
            try:
                await coro_factory()
                self._logger.warning(
                    f"Background task '{name}' exited unexpectedly. "
                    f"Restarting in {restart_delay}s"
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception(
                    f"Background task '{name}' crashed. "
                    f"Restarting in {restart_delay}s"
                )
            await asyncio.sleep(restart_delay)

    def _spawn_logged_task(self, coro, name: str | None = None) -> asyncio.Task:
        """Schedule a one-shot ``coro`` whose failure is logged, not swallowed.

        Use for fire-and-forget tasks that are not long-lived loops. Unlike a
        bare ``asyncio.create_task``, a failure is logged (with traceback) via a
        done-callback instead of being stored silently on an un-awaited task.
        For long-lived loops use ``_create_supervised_task`` instead.
        """
        task = asyncio.create_task(coro)
        task.add_done_callback(self.__log_task_exception)
        self.__background_tasks.append(task)
        return task

    def __log_task_exception(self, task: asyncio.Task) -> None:
        """Done-callback: surface a task's exception so it is never silent."""
        try:
            self.__background_tasks.remove(task)
        except ValueError:
            pass
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._logger.error(f"Background task failed: {exc!r}", exc_info=exc)

    def start(self) -> None:
        """Start the connector in a new thread.

        This method should be called to start the execution of this connector. It
        creates an event loop in a new thread and runs the connector in it.

        After calling start(), use join() to block until the connector is stopped.
        Use stop() to stop the connector.

        It:
        - calls self._connect() to connect to any external services.
        - creates and connects the robot sessions for the configured fleet
          (registering each robot's cameras, command handler and status callback).
        - runs the execution loop in a new thread.
        - calls self._disconnect() to disconnect from any external services once the
          connector is stopped.
        """

        # Prevent starting an already running thread
        if not self.__thread.is_alive():
            if self._metrics_server is not None:
                self._metrics_server.start()
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
        if self._metrics_server is not None:
            self._metrics_server.stop()
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
        if session is None:
            self._logger.debug(
                f"Skipping pose publish for '{robot_id}': no active session"
            )
            return
        with self.__fleet_lock:
            changed = frame_id != self.__last_published_frame_ids.get(robot_id)
            if changed:
                self.__last_published_frame_ids[robot_id] = frame_id
        if changed:
            self._logger.info(
                f"Updating map {frame_id} with new pose for robot {robot_id}."
            )
            # map/pose publish is I/O and should not hold the fleet lock
            self.publish_robot_map(robot_id, frame_id, is_update=True, session=session)
        session.publish_pose(x, y, yaw, frame_id, **kwargs)

    def publish_robot_map(
        self,
        robot_id: str,
        frame_id: str,
        is_update: bool = False,
        session: RobotSession | None = None,
    ) -> None:
        """Publish the map metadata for a specific robot to InOrbit.

        If the map is not found in the current configuration, an async fetch will be
        scheduled to retrieve the map from the robot. Once fetched, the map will be
        published automatically.

        Args:
            robot_id (str): The robot ID to publish map for
            frame_id (str): The frame ID of the map
            is_update (bool): Whether this is an update to an existing map
            session (RobotSession | None): The robot's session, if already resolved by
                the caller. When omitted it is resolved here; a robot removed
                concurrently is skipped rather than raising.
        """
        if session is None:
            session = self._get_robot_session(robot_id)
            if session is None:
                self._logger.debug(
                    f"Skipping map publish for '{robot_id}': no active session"
                )
                return
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
        if session is None:
            self._logger.debug(
                f"Skipping odometry publish for '{robot_id}': no active session"
            )
            return
        session.publish_odometry(**kwargs)

    def publish_robot_key_values(self, robot_id: str, **kwargs) -> None:
        """Publish key values for a specific robot to InOrbit.

        The ``connector_type`` key is injected automatically so the platform
        can identify the connector driving each robot. Subclasses may override
        it by passing their own ``connector_type`` keyword argument.

        Args:
            robot_id (str): The robot ID to publish key values for
            **kwargs: Key-value data
        """
        session = self._get_robot_session(robot_id)
        if session is None:
            self._logger.debug(
                f"Skipping key-values publish for '{robot_id}': no active session"
            )
            return
        session.publish_key_values({"connector_type": self._connector_type, **kwargs})

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
        with self.__fleet_lock:
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

        with self.__fleet_lock:
            sessions = dict(self.__robot_sessions)
            pending = self.__pending_system_stats
            self.__pending_system_stats = {}

        for robot_id, session in sessions.items():
            if pending_status := pending.get(robot_id):
                session.publish_system_stats(**pending_status)
            else:
                session.publish_system_stats(**default_values)

    # Methods meant to be extended by subclasses
    @abstractmethod
    async def _connect(self) -> None:
        """Connect to any external services.

        This method should not be called directly. Instead, call the start() method to
        start the connector. This ensures that the connector is only started once.

        self.update_fleet() (or add_robot()) may be called during this method to declare
        the fleet from an external source, e.g. fetching the robot list from a fleet
        manager API. Doing so creates the robot sessions immediately; otherwise they are
        created right after this method returns using data from the fleet configuration.
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

        Default implementation assumes robot is online if the connector is running.
        Override this method in specific connectors to provide robot-specific health
        checks (e.g., API connectivity, robot state, etc.).

        NOTE: State will automatically be requested from InOrbit if the robot is marked
        as offline but system stats are sent.

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

    @override
    def update_fleet(self, fleet: list[RobotConfig]) -> None:
        raise NotImplementedError(
            "update_fleet() is not supported on a single-robot Connector; "
            "use FleetConnector for multi-robot fleets"
        )

    @override
    def add_robot(self, robot_config: RobotConfig) -> None:
        raise NotImplementedError(
            "add_robot() is not supported on a single-robot Connector; "
            "use FleetConnector for multi-robot fleets"
        )

    @override
    def remove_robot(self, robot_id: str) -> None:
        raise NotImplementedError(
            "remove_robot() is not supported on a single-robot Connector; "
            "use FleetConnector for multi-robot fleets"
        )

    def __init__(self, robot_id: str, config: ConnectorRootConfig, **kwargs) -> None:
        """Initialize a new InOrbit connector.

        This class handles bidirectional communication with InOrbit.

        Args:
            robot_id (str): The ID of the InOrbit robot
            config (ConnectorRootConfig): The connector configuration. Pass a
                `ConnectorRootConfig` with a `fleet` field containing robot
                configurations. The one for the current robot will be selected
                by the `robot_id` parameter.

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
        fleet_config = config.to_singular_config(robot_id)
        super().__init__(fleet_config, **kwargs)

    def _get_session(self) -> RobotSession:
        """Get the edge-sdk robot session for the current robot.

        Usually the connector API is enough to abstract from the edge-sdk, but in some
        cases accessing the robot session directly may be necessary.

        Raises:
            KeyError: If the robot has no active session (e.g. accessed before the
                connector has connected, or after it stopped).
        """
        session = super()._get_robot_session(self.robot_id)
        if session is None:
            raise KeyError(f"No active session for robot '{self.robot_id}'")
        return session

    def _is_robot_online(self) -> bool:
        """Check if the robot is online.

        Default implementation assumes robot is online if connector is running.
        Override this method in specific connectors to provide robot-specific
        health checks (e.g., API connectivity, robot state, etc.).

        NOTE: State will automatically be requested from InOrbit if the robot is marked
        as offline but system stats are sent.

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
