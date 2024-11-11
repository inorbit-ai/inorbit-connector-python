#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import logging
import threading
from time import sleep

# Third Party
from inorbit_edge.models import RobotSessionModel
from inorbit_edge.robot import RobotSession
from inorbit_edge.video import OpenCVCamera

# InOrbit
from inorbit_connector.models import InorbitConnectorConfig


class Connector:
    """Generic InOrbit connector.

    This is the base class of an InOrbit connector. Subclasses should be implemented
    to override the execution_loop() method and optionally connect() and
    disconnect() methods (with calls to the superclass).
    """

    def __init__(self, robot_id: str, config: InorbitConnectorConfig) -> None:
        """Initialize a new InOrbit connector.

        This class handles bidirectional communication with InOrbit.

        Args:
            robot_id (str): The ID of the InOrbit robot
            config (InorbitConnectorConfig): The connector configuration
        """

        # Common information
        self.robot_id = robot_id
        self.config = config
        self._last_published_frame_id = None

        # Threading for the main run methods
        self.__stop_event = threading.Event()
        self.__thread = threading.Thread(target=self.__run)

        # Logging information
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(config.log_level.value)

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

    def _connect(self) -> None:
        """Connect to any external services.

        The base method handles connecting to InOrbit based on the provided
        configuration. Subclasses should override this method to connect to any
        external services ensuring to call the super method as well.

        This method should not be called directly. Instead, call the start() method to
        start the connector. This ensures that the connector is only started once.

        Raises:
            Exception: If the robot session cannot connect.
        """

        # Connect to InOrbit
        self._robot_session.connect()

    def _disconnect(self) -> None:
        """Disconnect from any external services.

        The base method handles disconnecting from InOrbit based on the provided
        configuration. Subclasses should override this method to disconnect from any
        external services ensuring to call the super method as well.

        This method should not be called directly. Instead, call the stop() method to
        stop the connector. This ensures that the connector is only stopped once.
        """

        # Disconnect from InOrbit
        self._robot_session.disconnect()

    # noinspection PyMethodMayBeStatic
    def _execution_loop(self) -> None:
        """The main execution loop for the connector.

        This method should be overridden by subclasses to provide the execution loop for
        the connector, will be called repeatedly until the connector is stopped, and
        should not be called directly. Instead, call the start() or stop() methods to
        start or stop the connector. This ensures that the connector is only started or
        stopped once.
        """

        # Overwrite this in subclass to something useful
        self._logger.warning("Execution loop is empty.")

    def publish_map(self, frame_id: str, is_update: bool = False) -> None:
        """Publish a map to InOrbit. If `frame_id` is not found in the maps
        configuration, this method will do nothing.
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
        """Start the execution loop of this connector.

        This method should be called to start the execution loop of this connector. It
        will block until the execution loop is started but run the loop on a new thread
        and will also call connect() to connect to any external services.
        """

        # Prevent starting already running thread
        if not self.__thread.is_alive():
            self.__stop_event.clear()

            # Connect to external services and create the InOrbit session
            self._connect()

            # Set up camera feeds
            for idx, camera_config in enumerate(self.config.cameras):
                self._logger.info(
                    f"Registering camera {idx}: {str(camera_config.video_url)}"
                )
                # If values are None, use default instead
                dump = camera_config.model_dump()
                clean = {k: v for k, v in dump.items() if v is not None}
                self._robot_session.register_camera(str(idx), OpenCVCamera(**clean))

            # Create new thread if an old thread finished
            self.__thread = threading.Thread(target=self.__run)
            self.__thread.start()

    def stop(self) -> None:
        """Stop the execution loop of this connector.

        This method should be called to stop the execution loop of this connector, will
        block until the execution loop is stopped, and will call disconnect() to clean
        up any external connections.
        """

        # Stop the execution loop
        self.__stop_event.set()
        self.__thread.join()

        # Cleanup external connections
        self._disconnect()

    def __run(self) -> None:
        """The main run thread method for the connector.

        This method will be called on a new thread and will run the execution loop of
        the connector until the stop event is set.
        """

        while not self.__stop_event.is_set():
            self._execution_loop()
            sleep(1.0 / self.config.update_freq)
