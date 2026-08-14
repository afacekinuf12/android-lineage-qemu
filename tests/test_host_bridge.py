import importlib.util
import io
import json
import pathlib
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "host_bridge", ROOT / "host_bridge" / "bridge.py"
)
BRIDGE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BRIDGE)


class HostBridgeTests(unittest.TestCase):
    def test_health_commands(self):
        self.assertEqual(
            BRIDGE.commands_for({"type": "health"}),
            [["get-state"], ["shell", "getprop", "sys.boot_completed"]],
        )

    def test_motion_command(self):
        commands = BRIDGE.commands_for(
            {
                "type": "motion",
                "accelerometer": [0, 9.8, 0],
                "magnetometer": [0, 5.9, -48.4],
                "gyroscope": [0, 0, 0],
            }
        )
        self.assertEqual(commands[0][:3], ["shell", "cuttlefish_sensor_injection", "motion"])
        self.assertEqual(len(commands[0]), 12)

    def test_rotation_validation(self):
        self.assertEqual(
            BRIDGE.commands_for({"type": "rotation", "degrees": 90}),
            [["shell", "cuttlefish_sensor_injection", "rotate", "90"]],
        )
        with self.assertRaises(ValueError):
            BRIDGE.commands_for({"type": "rotation", "degrees": 45})

    def test_battery_commands(self):
        self.assertEqual(
            BRIDGE.commands_for({"type": "battery", "level": 75, "status": 2}),
            [
                ["shell", "dumpsys", "battery", "set", "level", "75"],
                ["shell", "dumpsys", "battery", "set", "status", "2"],
            ],
        )

    def test_location_commands(self):
        commands = BRIDGE.commands_for(
            {
                "type": "location",
                "latitude": 37.3318,
                "longitude": -122.0312,
                "accuracy": 3.5,
            }
        )
        self.assertIn("add-test-provider gps", commands[0][-1])
        self.assertEqual(
            commands[1],
            [
                "shell",
                "cmd",
                "location",
                "providers",
                "set-test-provider-location",
                "gps",
                "--location",
                "37.3318,-122.0312",
                "--accuracy",
                "3.5",
            ],
        )

    def test_location_validation(self):
        with self.assertRaises(ValueError):
            BRIDGE.commands_for(
                {"type": "location", "latitude": 91, "longitude": 0}
            )

    def test_extended_battery_commands(self):
        commands = BRIDGE.commands_for(
            {
                "type": "battery",
                "level": 80,
                "status": 2,
                "present": True,
                "acPowered": True,
                "usbPowered": False,
                "temperature": 31.2,
            }
        )
        self.assertIn(
            ["shell", "dumpsys", "battery", "set", "present", "1"], commands
        )
        self.assertIn(["shell", "dumpsys", "battery", "set", "ac", "1"], commands)
        self.assertIn(["shell", "dumpsys", "battery", "set", "usb", "0"], commands)
        self.assertIn(
            ["shell", "dumpsys", "battery", "set", "temp", "312"], commands
        )

    def test_vector_validation(self):
        with self.assertRaises(ValueError):
            BRIDGE.commands_for(
                {
                    "type": "motion",
                    "accelerometer": [0, 1],
                    "magnetometer": [0, 0, 0],
                    "gyroscope": [0, 0, 0],
                }
            )

    def test_stale_event_is_rejected(self):
        message = json.dumps(
            {
                "type": "rotation",
                "degrees": 90,
                "timestampMs": 1000,
            }
        )
        with mock.patch.object(BRIDGE.time, "time", return_value=100):
            result = BRIDGE.run_stream(
                BRIDGE.AdbTarget("adb", None),
                True,
                stream=io.StringIO(message),
                max_event_age=30,
            )
        self.assertEqual(result, 1)

    def test_non_fail_fast_stream_continues_after_bad_event(self):
        class FakeExecutor:
            def __init__(self):
                self.commands = []

            def run(self, commands):
                self.commands.append(commands)

        executor = FakeExecutor()
        source = io.StringIO(
            '{"type":"rotation","degrees":45}\n'
            '{"type":"rotation","degrees":90}\n'
        )
        result = BRIDGE.run_stream(
            BRIDGE.AdbTarget("adb", None),
            False,
            stream=source,
            fail_fast=False,
            executor=executor,
        )
        self.assertEqual(result, 1)
        self.assertEqual(
            executor.commands,
            [[["shell", "cuttlefish_sensor_injection", "rotate", "90"]]],
        )

    def test_adb_executor_reconnects_network_target(self):
        target = BRIDGE.AdbTarget("adb", "127.0.0.1:5555")
        executor = BRIDGE.AdbExecutor(
            target,
            False,
            retries=1,
            retry_delay=0,
            command_timeout=5,
        )
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(
            BRIDGE.subprocess,
            "run",
            side_effect=[
                subprocess.CalledProcessError(1, ["adb"]),
                completed,
                completed,
                completed,
            ],
        ) as run:
            executor.run([["shell", "getprop", "sys.boot_completed"]])

        self.assertEqual(run.call_args_list[1].args[0], ["adb", "connect", "127.0.0.1:5555"])
        self.assertEqual(
            run.call_args_list[2].args[0],
            ["adb", "-s", "127.0.0.1:5555", "wait-for-device"],
        )
        self.assertEqual(
            run.call_args_list[3].args[0],
            [
                "adb",
                "-s",
                "127.0.0.1:5555",
                "shell",
                "getprop",
                "sys.boot_completed",
            ],
        )

    def test_status_reporter_writes_atomic_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "status.json"
            reporter = BRIDGE.StatusReporter(path)
            reporter.update("ready", lastEventType="health")
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["lastEventType"], "health")
        self.assertIn("updatedAtMs", payload)

    def test_server_refuses_to_replace_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "bridge.sock"
            path.write_text("not a socket", encoding="utf-8")
            with self.assertRaises(ValueError):
                BRIDGE.run_server(
                    path,
                    BRIDGE.AdbTarget("adb", None),
                    True,
                    retries=0,
                    retry_delay=0,
                    command_timeout=1,
                    max_event_age=30,
                    status_file=None,
                    health_interval=0,
                )

    def test_unix_socket_accepts_json_lines(self):
        class FakeExecutor:
            def __init__(self):
                self.commands = []

            def run(self, commands):
                self.commands.append(commands)

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "bridge.sock"
            executor = FakeExecutor()
            reporter = BRIDGE.StatusReporter(None)
            with BRIDGE.BridgeUnixServer(
                str(path), BRIDGE.BridgeRequestHandler
            ) as server:
                server.target = BRIDGE.AdbTarget("adb", None)
                server.dry_run = False
                server.max_event_age = 30
                server.reporter = reporter
                server.executor = executor
                worker = threading.Thread(target=server.handle_request)
                worker.start()
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.connect(str(path))
                    client.sendall(b'{"type":"rotation","degrees":180}\n')
                worker.join(timeout=2)
                self.assertFalse(worker.is_alive())

        self.assertEqual(
            executor.commands,
            [[["shell", "cuttlefish_sensor_injection", "rotate", "180"]]],
        )


if __name__ == "__main__":
    unittest.main()
