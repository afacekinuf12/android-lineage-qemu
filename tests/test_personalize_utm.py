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
            self.assertEqual(
                config["QEMU"]["AdditionalArguments"],
                [
                    "-smbios",
                    "type=1,manufacturer=OpenMobile,product=OpenMobile-One",
                    "-smbios",
                    "type=3,manufacturer=OpenMobile",
                ],
            )

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
