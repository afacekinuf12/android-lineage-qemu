#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
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
        return commands
    if message_type == "battery-reset":
        return [["shell", "dumpsys", "battery", "reset"]]
    raise ValueError(f"unsupported message type: {message_type!r}")


def run_stream(target: AdbTarget, dry_run: bool) -> int:
    for line_number, line in enumerate(sys.stdin, start=1):
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("message must be a JSON object")
            for command in commands_for(message):
                full_command = target.command(*command)
                if dry_run:
                    print(json.dumps(full_command))
                else:
                    subprocess.run(full_command, check=True)
        except (ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
            print(f"line {line_number}: {error}", file=sys.stderr)
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inject host hardware events into LineageOS for UTM."
    )
    parser.add_argument("--adb", default="adb", help="path to adb")
    parser.add_argument("--serial", help="ADB device serial")
    parser.add_argument(
        "--dry-run", action="store_true", help="print commands without executing them"
    )
    args = parser.parse_args()
    return run_stream(AdbTarget(args.adb, args.serial), args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
