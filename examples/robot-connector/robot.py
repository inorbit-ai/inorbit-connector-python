# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""
This file represents the collection of API wrappers that fetch information from the
robot.
"""

import asyncio
import random
import time
from typing import Coroutine

from inorbit_connector.metrics.http import (
    EndpointMapper,
    record_upstream_http_error,
    record_upstream_http_request,
)


_VENDOR = "example_bot"

# Bounded endpoint labels: any path matching one of the prefixes is collapsed
# to the right-hand label. Unknown paths fall through to "other" — the
# descriptor's `endpoint` label space is bounded by the number of rows in this
# table, NOT by the universe of URLs the upstream API can return.
_endpoint = EndpointMapper(
    [
        ("/api/v1/telemetry", "telemetry"),
        ("/api/v1/system_stats", "system_stats"),
        ("/api/v1/robot_status", "robot_status"),
    ]
)


async def _simulated_call(path: str) -> None:
    """Stand-in for a real httpx call. Sleeps + occasionally fails."""
    await asyncio.sleep(random.uniform(0.1, 0.3))
    if random.random() < 0.02:  # 2% simulated failure rate
        raise TimeoutError("simulated upstream timeout")


async def _do_request(method: str, path: str) -> None:
    """Wrap _simulated_call with canonical metric emission.

    In a real connector this is where you'd put the httpx/requests call.
    The pattern is identical: time it, record one helper on success, the
    other on failure, always pass ``endpoint`` through a normalizer.
    """
    start = time.perf_counter()
    try:
        await _simulated_call(path)
    except TimeoutError:
        record_upstream_http_error(
            vendor=_VENDOR,
            method=method,
            endpoint=_endpoint(path),
            error_kind="timeout",
            duration_seconds=time.perf_counter() - start,
        )
        raise
    except Exception:
        record_upstream_http_error(
            vendor=_VENDOR,
            method=method,
            endpoint=_endpoint(path),
            error_kind="other",
            duration_seconds=time.perf_counter() - start,
        )
        raise
    record_upstream_http_request(
        vendor=_VENDOR,
        method=method,
        endpoint=_endpoint(path),
        duration_seconds=time.perf_counter() - start,
    )


class ExampleBotAPIWrapper:
    """
    This class contains an async wrapper for the robot's API.
    Real API endpoints would be hit here.
    """

    def __init__(self, endpoint: str, api_key: str):
        self.endpoint = endpoint
        self.api_key = api_key

    async def fetch_telemetry_data(self) -> dict:
        """Simulate a request to the robot's telemetry API."""
        await _do_request("GET", "/api/v1/telemetry")
        return {
            "linear_speed": random.uniform(0.1, 0.9),
            "angular_speed": random.uniform(0.1, 0.9),
            "pose": {
                "x": random.uniform(0.1, 0.9),
                "y": random.uniform(0.1, 0.9),
                "yaw": random.uniform(0.1, 0.9),
                "frame_id": "frameIdA",
            },
        }

    async def fetch_system_stats(self) -> dict:
        """Simulate a request to the robot's system stats API."""
        await _do_request("GET", "/api/v1/system_stats")
        return {
            "cpu": random.uniform(0.1, 0.9),
            "ram": random.uniform(0.1, 0.9),
            "hdd": random.uniform(0.1, 0.9),
        }

    async def fetch_robot_status(self) -> dict:
        """Simulate a request to the robot's status API."""
        await _do_request("GET", "/api/v1/robot_status")
        return {
            "status": "running",
            "error": None,
            "message": "Robot is executing mission 123",
        }


class Robot:
    """
    This class contains the main logic fetching data from the robot.
    Each API endpoint is hit in a separate loop at its own specific frequency.
    The property accessors are used to get the latest fetched data from the robot.
    """

    def __init__(
        self,
        api_wrapper: ExampleBotAPIWrapper,
        default_update_freq: float,
    ):
        self._api_wrapper = api_wrapper
        self._stop_event = asyncio.Event()
        self._telemetry_data: dict = {}
        self._system_stats: dict = {}
        self._robot_status: dict = {}
        self._default_update_freq = default_update_freq
        self._running_tasks: list[asyncio.Task] = []

    def start(self) -> None:
        """Start the tasks that would fetch data from the robot."""
        self._run_in_loop(self._update_telemetry_data)
        self._run_in_loop(self._update_system_stats, frequency=2)
        self._run_in_loop(self._update_robot_status, frequency=2)

    async def stop(self) -> None:
        """Stop the tasks that would fetch data from the robot."""
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
        """Fetch the telemetry data from the robot."""
        self._telemetry_data = await self._api_wrapper.fetch_telemetry_data()

    async def _update_system_stats(self) -> None:
        """Fetch other less time-critical data from the robot."""
        self._system_stats = await self._api_wrapper.fetch_system_stats()

    async def _update_robot_status(self) -> None:
        """Fetch other less time-critical data from the robot."""
        self._robot_status = await self._api_wrapper.fetch_robot_status()

    @property
    def pose(self) -> dict | None:
        """Return the robot pose"""
        if pose := self._telemetry_data.get("pose"):
            if (
                pose.get("x")
                and pose.get("y")
                and pose.get("yaw")
                and pose.get("frame_id")
            ):
                return pose
        return None

    @property
    def odometry(self) -> dict | None:
        if self._telemetry_data.get("linear_speed") and self._telemetry_data.get(
            "angular_speed"
        ):
            return {
                "linear_speed": self._telemetry_data["linear_speed"],
                "angular_speed": self._telemetry_data["angular_speed"],
            }
        return None

    @property
    def system_stats(self) -> dict | None:
        if (
            self._system_stats.get("cpu")
            and self._system_stats.get("ram")
            and self._system_stats.get("hdd")
        ):
            return {
                "cpu_load_percentage": self._system_stats["cpu"],
                "ram_usage_percentage": self._system_stats["ram"],
                "hdd_usage_percentage": self._system_stats["hdd"],
            }
        return None

    @property
    def key_values(self) -> dict | None:
        return self._robot_status

    def _run_in_loop(self, coro: Coroutine, frequency: float | None = None) -> None:
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
