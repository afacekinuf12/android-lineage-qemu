import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "kernel_stage", Path(__file__).resolve().parents[1] / "scripts/stage-aosp-kernel.py")
STAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGE)


class KernelStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.source = self.root / "aosp"
        (self.source / ".repo").mkdir(parents=True)
        product = self.cache / "out/target/product/virtio_arm64only"
        self.objects = product / "obj/KERNEL_OBJ"
        (self.objects / "include/config").mkdir(parents=True)
        self.release = "6.12.81-4k-g123456789abc"
        (self.objects / "include/config/kernel.release").write_text(self.release)
        (product / ".kernel_version.txt").write_text(self.release)
        (self.objects / ".config").write_text("CONFIG_ARM64_4K_PAGES=y\n")
        boot = self.objects / "arch/arm64/boot"
        boot.mkdir(parents=True)
        (boot / "Image").write_bytes(bytes(56) + b"ARM\x64" + bytes(4))
        for name in ("btusb", "cfg80211", "virt_wifi", "zram", "zsmalloc"):
            (self.objects / (name + ".ko")).write_bytes(b"fixture-" + name.encode())
        self.report = self.root / "provenance.json"
        self.target = self.source / "device/virt/kernel-virtio/6.12/arm64/4k"

    def tearDown(self):
        self.temp.cleanup()

    def command(self, args, **kwargs):
        if args[0] == "modinfo":
            return self.release + " SMP preempt mod_unload aarch64"
        return "123456789abcdef0123456789abcdef0123456789"

    def stage(self):
        with patch.object(STAGE.subprocess, "check_output", side_effect=self.command):
            STAGE.stage(self.cache, self.source, self.report)

    def test_consistent_modules_staged_with_hashes_and_reusable(self):
        self.stage()
        self.stage()
        report = json.loads(self.report.read_text())
        self.assertEqual(6, len(report["files"]))
        for name, checksum in report["files"].items():
            self.assertEqual(checksum, STAGE.digest(self.target / name))

    def test_wrong_module_abi_is_rejected_before_staging(self):
        with patch.object(STAGE.subprocess, "check_output", return_value="6.1.0 SMP"):
            with self.assertRaisesRegex(ValueError, "ABI mismatch"):
                STAGE.stage(self.cache, self.source, self.report)
        self.assertFalse(self.target.exists())

    def test_missing_required_module_is_rejected(self):
        (self.objects / "virt_wifi.ko").unlink()
        with self.assertRaisesRegex(ValueError, "Missing kernel modules"):
            self.stage()
        self.assertFalse(self.target.exists())

    def test_changed_staged_kernel_is_not_silently_replaced(self):
        self.stage()
        (self.target / "kernel").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Existing staged kernel differs"):
            self.stage()
        self.assertEqual(b"changed", (self.target / "kernel").read_bytes())
