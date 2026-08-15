#!/usr/bin/env python3

import argparse
import io
import json
import math
import os
import socketserver
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class AdbTarget:
    adb: str
    serial: Optional[str]

    def command(self, *args: str) -> list[str]:
        command = [self.adb]
        if self.serial:
            command.extend(["-s", self.serial])
        command.extend(args)
        return command


class StatusReporter:
    def __init__(self, path: Optional[Path]) -> None:
        self.path = path
        self._lock = threading.Lock()

    def update(self, state: str, **details: Any) -> None:
        if self.path is None:
            return
        payload = {
            "state": state,
            "updatedAtMs": round(time.time() * 1000),
            **details,
        }
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)


class AdbExecutor:
    def __init__(
        self,
        target: AdbTarget,
        dry_run: bool,
        retries: int,
        retry_delay: float,
        command_timeout: float,
    ) -> None:
        self.target = target
        self.dry_run = dry_run
        self.retries = retries
        self.retry_delay = retry_delay
        self.command_timeout = command_timeout
        self._lock = threading.Lock()

    def _reconnect(self) -> None:
        if self.target.serial and ":" in self.target.serial:
            subprocess.run(
                [self.target.adb, "connect", self.target.serial],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.command_timeout,
            )
        subprocess.run(
            self.target.command("wait-for-device"),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=self.command_timeout,
        )

    def run(self, commands: list[list[str]], quiet: bool = False) -> None:
        with self._lock:
            if self.dry_run:
                for command in commands:
                    print(json.dumps(self.target.command(*command)))
                return

            for attempt in range(self.retries + 1):
                try:
                    for command in commands:
                        subprocess.run(
                            self.target.command(*command),
                            check=True,
                            stdout=(
                                subprocess.DEVNULL if quiet else None
                            ),
                            stderr=(
                                subprocess.DEVNULL if quiet else None
                            ),
                            timeout=self.command_timeout,
                        )
                    return
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    if attempt >= self.retries:
                        raise
                    time.sleep(self.retry_delay)
                    try:
                        self._reconnect()
                    except (
                        subprocess.CalledProcessError,
                        subprocess.TimeoutExpired,
                    ):
                        continue


def _vector(message: dict[str, Any], name: str) -> list[str]:
    value = message.get(name)
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{name} must contain exactly three numbers")
    if not all(isinstance(item, (int, float)) for item in value):
        raise ValueError(f"{name} must contain only numbers")
    return [str(item) for item in value]


def _number(
    message: dict[str, Any],
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    value = message.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return float(value)


def commands_for(message: dict[str, Any]) -> list[list[str]]:
    message_type = message.get("type")
    if message_type == "health":
        return [["get-state"], ["shell", "getprop", "sys.boot_completed"]]
    if message_type == "motion":
        values = (
            _vector(message, "accelerometer")
            + _vector(message, "magnetometer")
            + _vector(message, "gyroscope")
        )
        return [["shell", "cuttlefish_sensor_injection", "motion", *values]]
    if message_type == "rotation":
        degrees = message.get("degrees")
        if not isinstance(degrees, int) or degrees not in (0, 90, 180, 270):
            raise ValueError("degrees must be one of 0, 90, 180, or 270")
        return [["shell", "cuttlefish_sensor_injection", "rotate", str(degrees)]]
    if message_type == "location":
        latitude = _number(message, "latitude", -90, 90)
        longitude = _number(message, "longitude", -180, 180)
        accuracy = (
            _number(message, "accuracy", 0, 10000)
            if "accuracy" in message
            else 5.0
        )
        coordinates = f"{latitude},{longitude}"
        setup = (
            "cmd location set-location-enabled true; "
            "cmd location providers add-test-provider gps "
            "--requiresSatellite --supportsAltitude --supportsSpeed "
            "--supportsBearing >/dev/null 2>&1 || true; "
            "cmd location providers set-test-provider-enabled gps true"
        )
        return [
            ["shell", "sh", "-c", setup],
            [
                "shell",
                "cmd",
                "location",
                "providers",
                "set-test-provider-location",
                "gps",
                "--location",
                coordinates,
                "--accuracy",
                str(accuracy),
            ],
        ]
    if message_type == "location-reset":
        reset = (
            "cmd location providers set-test-provider-enabled gps false "
            ">/dev/null 2>&1 || true; "
            "cmd location providers remove-test-provider gps "
            ">/dev/null 2>&1 || true"
        )
        return [["shell", "sh", "-c", reset]]
    if message_type == "battery":
        level = message.get("level")
        if not isinstance(level, int) or not 0 <= level <= 100:
            raise ValueError("battery level must be an integer from 0 to 100")
        status = message.get("status", 2)
        if not isinstance(status, int) or not 1 <= status <= 5:
            raise ValueError("battery status must be an integer from 1 to 5")
        commands = [
            ["shell", "dumpsys", "battery", "set", "level", str(level)],
            ["shell", "dumpsys", "battery", "set", "status", str(status)],
        ]
        optional_boolean_fields = {
            "present": "present",
            "acPowered": "ac",
            "usbPowered": "usb",
            "wirelessPowered": "wireless",
        }
        for field, battery_property in optional_boolean_fields.items():
            value = message.get(field)
            if value is not None:
                if not isinstance(value, bool):
                    raise ValueError(f"{field} must be a boolean")
                commands.append(
                    [
                        "shell",
                        "dumpsys",
                        "battery",
                        "set",
                        battery_property,
                        "1" if value else "0",
                    ]
                )
        if "temperature" in message:
            temperature = _number(message, "temperature", -50, 100)
            commands.append(
                [
                    "shell",
                    "dumpsys",
                    "battery",
                    "set",
                    "temp",
                    str(round(temperature * 10)),
                ]
            )
        if "capacityMah" in message:
            capacity_mah = _number(message, "capacityMah", 100, 20000)
            charge_counter_uah = round(capacity_mah * 1000 * level / 100)
            commands.append(
                [
                    "shell",
                    "dumpsys",
                    "battery",
                    "set",
                    "counter",
                    str(charge_counter_uah),
                ]
            )
        return commands
    if message_type == "battery-reset":
        return [["shell", "dumpsys", "battery", "reset"]]
    raise ValueError(f"unsupported message type: {message_type!r}")


def _validate_event_time(
    message: dict[str, Any],
    max_event_age: Optional[float],
    now: float,
) -> None:
    if "timestampMs" not in message:
        return
    timestamp = message["timestampMs"]
    if (
        not isinstance(timestamp, (int, float))
        or isinstance(timestamp, bool)
        or not math.isfinite(timestamp)
    ):
        raise ValueError("timestampMs must be a finite number")
    age = now * 1000 - timestamp
    if age < -300000:
        raise ValueError("timestampMs is more than five minutes in the future")
    if max_event_age is not None and age > max_event_age * 1000:
        raise ValueError(f"event is older than {max_event_age} seconds")


def run_stream(
    target: AdbTarget,
    dry_run: bool,
    *,
    stream: Any = None,
    retries: int = 3,
    retry_delay: float = 1.0,
    command_timeout: float = 15.0,
    max_event_age: Optional[float] = 30.0,
    fail_fast: bool = True,
    reporter: Optional[StatusReporter] = None,
    executor: Optional[AdbExecutor] = None,
) -> int:
    source = stream if stream is not None else sys.stdin
    status = reporter or StatusReporter(None)
    runner = executor or AdbExecutor(
        target, dry_run, retries, retry_delay, command_timeout
    )
    failed = False
    for line_number, line in enumerate(source, start=1):
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("message must be a JSON object")
            _validate_event_time(message, max_event_age, time.time())
            runner.run(commands_for(message))
            status.update("ready", lastEventType=message.get("type"))
        except (
            ValueError,
            json.JSONDecodeError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as error:
            print(f"line {line_number}: {error}", file=sys.stderr)
            status.update("error", line=line_number, error=str(error))
            failed = True
            if fail_fast:
                return 1
    return 1 if failed else 0


class BridgeUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class BridgeRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        source = io.TextIOWrapper(self.rfile, encoding="utf-8")
        run_stream(
            self.server.target,
            self.server.dry_run,
            stream=source,
            fail_fast=False,
            max_event_age=self.server.max_event_age,
            reporter=self.server.reporter,
            executor=self.server.executor,
        )


def run_server(
    socket_path: Path,
    target: AdbTarget,
    dry_run: bool,
    *,
    retries: int,
    retry_delay: float,
    command_timeout: float,
    max_event_age: Optional[float],
    status_file: Optional[Path],
    health_interval: float,
) -> int:
    if socket_path.exists():
        if not stat.S_ISSOCK(socket_path.stat().st_mode):
            raise ValueError(f"refusing to replace non-socket path: {socket_path}")
        socket_path.unlink()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    reporter = StatusReporter(status_file)
    executor = AdbExecutor(
        target, dry_run, retries, retry_delay, command_timeout
    )
    stop_health = threading.Event()

    def health_loop() -> None:
        while not stop_health.is_set():
            try:
                executor.run(commands_for({"type": "health"}), quiet=True)
                reporter.update("ready", adb="online", socket=str(socket_path))
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                reporter.update("error", adb="offline", error=str(error))
            stop_health.wait(health_interval)

    reporter.update("starting", socket=str(socket_path))
    with BridgeUnixServer(str(socket_path), BridgeRequestHandler) as server:
        server.target = target
        server.dry_run = dry_run
        server.max_event_age = max_event_age
        server.reporter = reporter
        server.executor = executor
        os.chmod(socket_path, 0o600)
        reporter.update("ready", socket=str(socket_path))
        health = None
        if health_interval > 0:
            health = threading.Thread(
                target=health_loop,
                name="adb-health",
                daemon=True,
            )
            health.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop_health.set()
            if health is not None:
                health.join(timeout=command_timeout + 1)
            reporter.update("stopped", socket=str(socket_path))
    socket_path.unlink(missing_ok=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inject host hardware events into LineageOS for UTM."
    )
    parser.add_argument("--adb", default="adb", help="path to adb")
    parser.add_argument("--serial", help="ADB device serial")
    parser.add_argument("--listen", type=Path, help="serve JSON Lines on a Unix socket")
    parser.add_argument("--status-file", type=Path, help="write bridge health as JSON")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=1.0)
    parser.add_argument("--command-timeout", type=float, default=15.0)
    parser.add_argument(
        "--health-interval",
        type=float,
        default=10.0,
        help="seconds between ADB health checks; zero disables checks",
    )
    parser.add_argument(
        "--max-event-age",
        type=float,
        default=30.0,
        help="reject timestamped events older than this many seconds",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print commands without executing them"
    )
    args = parser.parse_args()
    if args.retries < 0:
        parser.error("--retries must not be negative")
    if args.retry_delay < 0:
        parser.error("--retry-delay must not be negative")
    if args.command_timeout <= 0:
        parser.error("--command-timeout must be positive")
    if args.health_interval < 0:
        parser.error("--health-interval must not be negative")
    if args.max_event_age < 0:
        parser.error("--max-event-age must not be negative")

    target = AdbTarget(args.adb, args.serial)
    if args.listen:
        return run_server(
            args.listen,
            target,
            args.dry_run,
            retries=args.retries,
            retry_delay=args.retry_delay,
            command_timeout=args.command_timeout,
            max_event_age=args.max_event_age,
            status_file=args.status_file,
            health_interval=args.health_interval,
        )
    return run_stream(
        target,
        args.dry_run,
        retries=args.retries,
        retry_delay=args.retry_delay,
        command_timeout=args.command_timeout,
        max_event_age=args.max_event_age,
        reporter=StatusReporter(args.status_file),
    )


if __name__ == "__main__":
    raise SystemExit(main())
