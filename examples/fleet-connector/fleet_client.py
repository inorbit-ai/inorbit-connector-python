# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""
This file represents a fleet manager API client that fetches information for
multiple robots at once.
"""

import asyncio
import random


class FleetManagerAPIWrapper:
    """
    This class contains an async wrapper for the fleet manager's API.
    In a real implementation, this would make HTTP requests to the fleet
    manager's REST API endpoints to get data for all robots.
    """

    def __init__(self, endpoint: str, api_key: str):
        self.endpoint = endpoint
        self.api_key = api_key

    async def fetch_fleet_telemetry_data(self, robot_ids: list[str]) -> dict:
        """Simulate a request to the fleet manager's telemetry API.

        Returns data for all robots in the fleet.

        Args:
            robot_ids: List of robot IDs to fetch data for

        Returns:
            Dictionary mapping robot_id to telemetry data
        """
        await asyncio.sleep(random.uniform(0.1, 0.3))

        telemetry_data = {}
        for robot_id in robot_ids:
            # Extract robot index for simulation
            robot_index = int(robot_id.split("-")[-1])

            telemetry_data[robot_id] = {
                "linear_speed": random.uniform(0.1, 0.9) + (robot_index * 0.05),
                "angular_speed": random.uniform(0.1, 0.9) + (robot_index * 0.02),
                "pose": {
                    "x": random.uniform(-5.0, 5.0) + (robot_index * 10.0),
                    "y": random.uniform(-5.0, 5.0) + (robot_index * 10.0),
                    "yaw": random.uniform(-3.14, 3.14),
                    "frame_id": "frameIdA",
                },
            }

        return telemetry_data

    async def fetch_fleet_system_stats(self, robot_ids: list[str]) -> dict:
        """Simulate a request to the fleet manager's system stats API.

        Returns system stats for all robots in the fleet.

        Args:
            robot_ids: List of robot IDs to fetch data for

        Returns:
            Dictionary mapping robot_id to system stats
        """
        await asyncio.sleep(random.uniform(0.1, 0.3))

        stats_data = {}
        for robot_id in robot_ids:
            stats_data[robot_id] = {
                "cpu": random.uniform(0.1, 0.9),
                "ram": random.uniform(0.2, 0.8),
                "hdd": random.uniform(0.3, 0.7),
            }

        return stats_data

    async def fetch_fleet_robot_status(self, robot_ids: list[str]) -> dict:
        """Simulate a request to the fleet manager's robot status API.

        Returns status information for all robots in the fleet.

        Args:
            robot_ids: List of robot IDs to fetch data for

        Returns:
            Dictionary mapping robot_id to status data
        """
        await asyncio.sleep(random.uniform(0.1, 0.3))

        status_data = {}
        for robot_id in robot_ids:
            robot_index = int(robot_id.split("-")[-1])

            statuses = ["idle", "running", "charging", "error"]
            status = random.choice(statuses[:3])  # Avoid errors for demo

            status_data[robot_id] = {
                "status": status,
                "error": None,
                "message": f"Robot {robot_id} is {status}",
                "battery_level": random.uniform(0.3, 1.0),
                "mission_id": f"mission_{robot_index}",
            }

        return status_data


class FleetManager:
    """
    This class manages the fleet data by polling the fleet manager API.
    Each API endpoint is hit at its own specific frequency.
    The property accessors are used to get the latest fetched data for specific robots.
    """

    def __init__(
        self,
        robot_ids: list[str],
        api_wrapper: FleetManagerAPIWrapper,
        default_update_freq: float,
    ):
        self.robot_ids = robot_ids
        self._api_wrapper = api_wrapper
        self._stop_event = asyncio.Event()
        self._telemetry_data: dict[str, dict] = {}
        self._system_stats: dict[str, dict] = {}
        self._robot_status: dict[str, dict] = {}
        self._default_update_freq = default_update_freq
        self._running_tasks: list[asyncio.Task] = []

    def start(self) -> None:
        """Start the tasks that fetch data from the fleet manager."""
        self._run_in_loop(self._update_telemetry_data)
        self._run_in_loop(self._update_system_stats, frequency=0.5)
        self._run_in_loop(self._update_robot_status, frequency=0.5)

    async def stop(self) -> None:
        """Stop the tasks that fetch data from the fleet manager."""
        # Signal all tasks to stop
        self._stop_event.set()

        # Give tasks a chance to exit gracefully
        if self._running_tasks:
            try:
                # Wait for tasks to complete with a timeout
                done, pending = await asyncio.wait(
                    self._running_tasks,
                    timeout=1.0,  # Allow 1 second for graceful shutdown
                    return_when=asyncio.ALL_COMPLETED,
                )

                # Only cancel tasks that didn't finish in time
                for task in pending:
                    task.cancel()

                # Wait briefly for cancellations to process
                if pending:
                    await asyncio.wait(pending, timeout=0.5)

            except Exception as e:
                print(f"Error during graceful shutdown: {e}")

        # Clear the task list
        self._running_tasks.clear()

    async def _update_telemetry_data(self) -> None:
        """Fetch the telemetry data from the fleet manager for all robots."""
        self._telemetry_data = await self._api_wrapper.fetch_fleet_telemetry_data(
            self.robot_ids
        )

    async def _update_system_stats(self) -> None:
        """Fetch system stats from the fleet manager for all robots."""
        self._system_stats = await self._api_wrapper.fetch_fleet_system_stats(
            self.robot_ids
        )

    async def _update_robot_status(self) -> None:
        """Fetch robot status from the fleet manager for all robots."""
        self._robot_status = await self._api_wrapper.fetch_fleet_robot_status(
            self.robot_ids
        )

    def get_robot_pose(self, robot_id: str) -> dict | None:
        """Return the pose for a specific robot."""
        if robot_id not in self._telemetry_data:
            return None

        telemetry = self._telemetry_data[robot_id]
        if pose := telemetry.get("pose"):
            if (
                pose.get("x") is not None
                and pose.get("y") is not None
                and pose.get("yaw") is not None
                and pose.get("frame_id")
            ):
                return pose
        return None

    def get_robot_odometry(self, robot_id: str) -> dict | None:
        """Return the odometry for a specific robot."""
        if robot_id not in self._telemetry_data:
            return None

        telemetry = self._telemetry_data[robot_id]
        if (
            telemetry.get("linear_speed") is not None
            and telemetry.get("angular_speed") is not None
        ):
            return {
                "linear_speed": telemetry["linear_speed"],
                "angular_speed": telemetry["angular_speed"],
            }
        return None

    def get_robot_system_stats(self, robot_id: str) -> dict | None:
        """Return the system stats for a specific robot."""
        if robot_id not in self._system_stats:
            return None

        stats = self._system_stats[robot_id]
        if (
            stats.get("cpu") is not None
            and stats.get("ram") is not None
            and stats.get("hdd") is not None
        ):
            return {
                "cpu_load_percentage": stats["cpu"],
                "ram_usage_percentage": stats["ram"],
                "hdd_usage_percentage": stats["hdd"],
            }
        return None

    def get_robot_key_values(self, robot_id: str) -> dict | None:
        """Return the key values for a specific robot."""
        if robot_id not in self._robot_status:
            return None
        return self._robot_status[robot_id]

    def _run_in_loop(self, coro, frequency: float | None = None) -> None:
        """Run a coroutine in a loop at a specified frequency. If no frequency is
        provided, the default update frequency will be used."""

        async def loop():
            try:
                while not self._stop_event.is_set():
                    try:
                        # Check stop_event between each iteration
                        if self._stop_event.is_set():
                            break

                        await asyncio.gather(
                            coro(),
                            asyncio.sleep(1 / (frequency or self._default_update_freq)),
                        )
                    except asyncio.CancelledError:
                        # Handle cancellation gracefully
                        break
                    except Exception as e:
                        print(f"Error in loop running {coro.__name__}: {e}")
                        # Shorter sleep during errors to check stop_event more
                        # frequently
                        await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                # Exit cleanly when cancelled
                pass

        self._running_tasks.append(asyncio.create_task(loop()))
