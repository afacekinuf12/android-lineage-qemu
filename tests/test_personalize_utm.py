import importlib.util
import pathlib
import plistlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "personalize_utm", ROOT / "tools" / "personalize-utm.py"
)
PERSONALIZE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PERSONALIZE)


class PersonalizeUtmTests(unittest.TestCase):
    def test_locally_administered_unicast_mac(self):
        with mock.patch.object(PERSONALIZE.secrets, "token_bytes", return_value=b"\0" * 6):
            mac = PERSONALIZE.locally_administered_mac()
        self.assertEqual(mac, "02:00:00:00:00:00")

    def test_updates_uuid_name_and_all_networks(self):
        with tempfile.TemporaryDirectory() as directory:
            vm = pathlib.Path(directory) / "device.utm"
            vm.mkdir()
            config_path = vm / "config.plist"
            with config_path.open("wb") as destination:
                plistlib.dump(
                    {
                        "Information": {"UUID": "old", "Name": "old"},
                        "Network": [{"MacAddress": "old"}, {"MacAddress": "old"}],
                    },
                    destination,
                )

            with mock.patch(
                "sys.argv", ["personalize-utm.py", str(vm), "--name", "Device A"]
            ):
                self.assertEqual(PERSONALIZE.main(), 0)

            with config_path.open("rb") as source:
                config = plistlib.load(source)
            self.assertNotEqual(config["Information"]["UUID"], "old")
            self.assertEqual(config["Information"]["Name"], "Device A")
            self.assertEqual(len({item["MacAddress"] for item in config["Network"]}), 2)
            for network in config["Network"]:
                first_octet = int(network["MacAddress"].split(":")[0], 16)
                self.assertEqual(first_octet & 0x03, 0x02)

    def test_default_name_uses_public_product_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            vm = pathlib.Path(directory) / "device.utm"
            vm.mkdir()
            config_path = vm / "config.plist"
            with config_path.open("wb") as destination:
                plistlib.dump(
                    {"Information": {"UUID": "old", "Name": "old"}}, destination
                )

            with mock.patch("sys.argv", ["personalize-utm.py", str(vm)]):
                self.assertEqual(PERSONALIZE.main(), 0)

            with config_path.open("rb") as source:
                config = plistlib.load(source)
            self.assertEqual(config["Information"]["Name"], "OpenMobile One")

    def test_pixel_9_pro_hardware_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            vm = pathlib.Path(directory) / "device.utm"
            vm.mkdir()
            config_path = vm / "config.plist"
            with config_path.open("wb") as destination:
                plistlib.dump(
                    {
                        "Information": {"UUID": "old", "Name": "old"},
                        "System": {"CPUCount": 4, "MemorySize": 4096},
                        "Display": [{"DynamicResolution": True}],
                        "QEMU": {"AdditionalArguments": []},
                    },
                    destination,
                )

            with mock.patch(
                "sys.argv",
                [
                    "personalize-utm.py",
                    str(vm),
                    "--hardware-profile",
                    "pixel-9-pro-compat",
                ],
            ):
                self.assertEqual(PERSONALIZE.main(), 0)

            with config_path.open("rb") as source:
                config = plistlib.load(source)
            self.assertEqual(config["System"]["CPUCount"], 8)
            self.assertEqual(config["System"]["MemorySize"], 16384)
            self.assertFalse(config["Display"][0]["DynamicResolution"])
            arguments = config["QEMU"]["AdditionalArguments"]
            self.assertIn("-smbios", arguments)
            self.assertTrue(
                any("type=0,vendor=OpenMobile,version=OpenMobile-1.0" == a for a in arguments)
            )
            self.assertTrue(
                any("type=3,manufacturer=OpenMobile" == a for a in arguments)
            )
            type1 = next(a for a in arguments if a.startswith("type=1,"))
            self.assertIn("manufacturer=OpenMobile", type1)
            self.assertIn("product=OpenMobile-One", type1)
            self.assertRegex(type1, r"serial=OM[0-9A-F]{14}")

    def test_profile_is_idempotent_and_preserves_serial(self):
        with tempfile.TemporaryDirectory() as directory:
            vm = pathlib.Path(directory) / "device.utm"
            vm.mkdir()
            config_path = vm / "config.plist"
            with config_path.open("wb") as destination:
                plistlib.dump(
                    {
                        "Information": {"UUID": "fixed", "Name": "fixed"},
                        "System": {"CPUCount": 4, "MemorySize": 4096},
                        "Display": [{"DynamicResolution": True}],
                        "QEMU": {"AdditionalArguments": []},
                    },
                    destination,
                )

            argv = [
                "personalize-utm.py",
                str(vm),
                "--preserve-identity",
                "--hardware-profile",
                "pixel-9-pro-compat",
            ]
            with mock.patch("sys.argv", argv):
                self.assertEqual(PERSONALIZE.main(), 0)
            with config_path.open("rb") as source:
                first = plistlib.load(source)["QEMU"]["AdditionalArguments"]
            serial = PERSONALIZE.existing_serial(first)
            self.assertTrue(serial.startswith("OM"))

            # Re-applying with --preserve-identity keeps the serial and does not
            # accumulate duplicate managed SMBIOS pairs.
            with mock.patch("sys.argv", argv):
                self.assertEqual(PERSONALIZE.main(), 0)
            with config_path.open("rb") as source:
                second = plistlib.load(source)["QEMU"]["AdditionalArguments"]
            self.assertEqual(first, second)
            self.assertEqual(PERSONALIZE.existing_serial(second), serial)
            self.assertEqual(second.count("-smbios"), 3)

    def test_preserves_existing_identity_when_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            vm = pathlib.Path(directory) / "device.utm"
            vm.mkdir()
            config_path = vm / "config.plist"
            with config_path.open("wb") as destination:
                plistlib.dump(
                    {
                        "Information": {"UUID": "fixed", "Name": "fixed"},
                        "Network": [{"MacAddress": "fixed"}],
                    },
                    destination,
                )

            with mock.patch(
                "sys.argv",
                ["personalize-utm.py", str(vm), "--preserve-identity"],
            ):
                self.assertEqual(PERSONALIZE.main(), 0)

            with config_path.open("rb") as source:
                config = plistlib.load(source)
            self.assertEqual(config["Information"]["UUID"], "fixed")
            self.assertEqual(config["Information"]["Name"], "fixed")
            self.assertEqual(config["Network"][0]["MacAddress"], "fixed")


if __name__ == "__main__":
    unittest.main()
