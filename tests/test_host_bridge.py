import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "host_bridge", ROOT / "host_bridge" / "bridge.py"
)
BRIDGE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BRIDGE)


class HostBridgeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
