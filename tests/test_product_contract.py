import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "product_contract", ROOT / "scripts/verify-product-contract.py")
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


class ProductContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fingerprint = ("google/lineage_virtio_arm64only/virtio_arm64only:"
                            "16/ACTUAL.20260914/20260914:user/release-keys")
        (self.root / "build_fingerprint-lineage_virtio_arm64only.txt").write_text(
            self.fingerprint + "\n")
        self.write_partition("system", True)
        self.write_partition("vendor")
        self.write_partition("product", True, etc=True)
        self.permissions = self.root / "vendor/etc/permissions"
        self.permissions.mkdir(parents=True)
        self.write_features()

    def tearDown(self):
        self.temp.cleanup()

    def write_partition(self, partition, global_props=False, etc=False):
        path = self.root / partition / ("etc/build.prop" if etc else "build.prop")
        path.parent.mkdir(parents=True, exist_ok=True)
        props = {}
        prefixes = ["ro." + partition + ".build"]
        if global_props:
            prefixes.append("ro.build")
        for prefix in prefixes:
            props.update({
                prefix + ".fingerprint": self.fingerprint,
                prefix + ".id": "ACTUAL.20260914",
                prefix + ".version.incremental": "20260914",
                prefix + ".version.release": "16",
                prefix + ".type": "user",
                prefix + ".tags": "release-keys",
                prefix + ".version.security_patch": "2026-08-01",
            })
        path.write_text("".join("{}={}\n".format(k, v) for k, v in props.items()))
        return path

    def write_features(self, extra=()):
        features = sorted(CONTRACT.SENSOR_FEATURES | set(extra))
        (self.permissions / "motion.xml").write_text(
            "<permissions>" + "".join('<feature name="{}"/>'.format(x) for x in features)
            + "</permissions>")

    def replace(self, path, old, new):
        path.write_text(path.read_text().replace(old, new))

    def test_actual_build_target_is_accepted(self):
        result = CONTRACT.verify(self.root)
        self.assertTrue(result["accepted"], result["errors"])
        self.assertEqual(5, len(result["checked_builds"]))

    def test_old_phone_fingerprint_fails_even_with_release_keys(self):
        path = self.root / "system/build.prop"
        old = "google/caiman/caiman:16/BP4A.260205.001/13561507:user/release-keys"
        self.replace(path, self.fingerprint, old)
        errors = CONTRACT.verify(self.root)["errors"]
        self.assertTrue(any("generated build fingerprint" in e for e in errors))
        self.assertTrue(any("fingerprint token differs" in e for e in errors))

    def test_each_tuple_member_must_match(self):
        path = self.root / "vendor/build.prop"
        original = path.read_text()
        for suffix in (".id", ".version.incremental", ".type", ".tags", ".version.release"):
            with self.subTest(suffix=suffix):
                path.write_text(original)
                props = CONTRACT.properties(path)
                key = "ro.vendor.build" + suffix
                self.replace(path, key + "=" + props[key], key + "=WRONG")
                self.assertFalse(CONTRACT.verify(self.root)["accepted"])

    def test_preview_codename_uses_release_or_codename(self):
        self.fingerprint = self.fingerprint.replace(":16/", ":Preview/")
        (self.root / "build_fingerprint-lineage_virtio_arm64only.txt").write_text(self.fingerprint)
        for partition, global_props, etc in (("system", True, False), ("vendor", False, False),
                                             ("product", True, True)):
            path = self.write_partition(partition, global_props, etc)
            with path.open("a") as stream:
                stream.write("ro.{}.build.version.release_or_codename=Preview\n".format(partition))
                if global_props:
                    stream.write("ro.build.version.release_or_codename=Preview\n")
        self.assertTrue(CONTRACT.verify(self.root)["accepted"])

    def test_security_patch_disagreement_fails(self):
        self.replace(self.root / "product/etc/build.prop",
                     "ro.build.version.security_patch=2026-08-01",
                     "ro.build.version.security_patch=2025-12-05")
        self.assertFalse(CONTRACT.verify(self.root)["accepted"])

    def test_missing_required_partition_fails(self):
        (self.root / "system/build.prop").unlink()
        self.assertFalse(CONTRACT.verify(self.root)["accepted"])

    def test_existing_optional_partition_requires_metadata(self):
        (self.root / "system_ext").mkdir()
        self.assertFalse(CONTRACT.verify(self.root)["accepted"])

    def test_partition_override_cannot_escape_check(self):
        path = self.write_partition("odm", etc=True)
        self.replace(path, "ro.odm.build.id=ACTUAL.20260914", "ro.odm.build.id=OLD")
        self.assertFalse(CONTRACT.verify(self.root)["accepted"])

    def test_missing_canonical_file_is_not_pass(self):
        (self.root / "build_fingerprint-lineage_virtio_arm64only.txt").unlink()
        with self.assertRaises(OSError):
            CONTRACT.verify(self.root)

    def test_duplicate_property_conflict_rejected(self):
        path = self.root / "system/build.prop"
        with path.open("a") as stream:
            stream.write("ro.build.id=OTHER\n")
        with self.assertRaisesRegex(ValueError, "conflicting property"):
            CONTRACT.verify(self.root)

    def test_unfinalized_properties_rejected(self):
        self.replace(self.root / "vendor/build.prop", ".fingerprint=", ".fingerprint?=")
        with self.assertRaises(ValueError):
            CONTRACT.verify(self.root)

    def test_feature_version_zero_still_means_declared(self):
        path = self.permissions / "motion.xml"
        self.replace(path, '"/>', '" version="0"/>')
        self.assertTrue(CONTRACT.verify(self.root)["accepted"])

    def test_extra_sensor_rejected_regardless_of_xml_filename(self):
        self.write_features(["android.hardware.sensor.hinge_angle"])
        self.assertFalse(CONTRACT.verify(self.root)["accepted"])

    def test_stale_product_sensor_xml_rejected(self):
        path = self.root / "product/etc/sysconfig/old.xml"
        path.parent.mkdir(parents=True)
        path.write_text('<config><feature name="android.hardware.sensor.barometer"/></config>')
        self.assertFalse(CONTRACT.verify(self.root)["accepted"])

    def test_missing_motion_feature_fails(self):
        self.replace(self.permissions / "motion.xml",
                     '<feature name="android.hardware.sensor.gyroscope"/>', "")
        self.assertFalse(CONTRACT.verify(self.root)["accepted"])

    def test_unavailable_feature_does_not_hide_stale_claim(self):
        self.write_features(["android.hardware.sensor.hinge_angle"])
        path = self.permissions / "mask.xml"
        path.write_text('<permissions><unavailable-feature '
                        'name="android.hardware.sensor.hinge_angle"/></permissions>')
        self.assertFalse(CONTRACT.verify(self.root)["accepted"])

    def test_unavailable_motion_feature_fails(self):
        (self.permissions / "mask.xml").write_text(
            '<permissions><unavailable-feature '
            'name="android.hardware.sensor.compass"/></permissions>')
        self.assertFalse(CONTRACT.verify(self.root)["accepted"])

    def test_cli_exit_status(self):
        cmd = [sys.executable, str(ROOT / "scripts/verify-product-contract.py"), str(self.root)]
        passed = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        self.assertEqual(0, passed.returncode, passed.stderr)
        self.assertTrue(json.loads(passed.stdout)["accepted"])
        self.write_features(["android.hardware.sensor.light"])
        failed = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        self.assertEqual(1, failed.returncode)
        self.assertFalse(json.loads(failed.stdout)["accepted"])


class BuildIntegrationTests(unittest.TestCase):
    def test_product_patch_uses_generated_fingerprint(self):
        patch = (ROOT / "patches/0007-virtio-arm64-consistent-product-identity.patch").read_text()
        added = "\n".join(x[1:] for x in patch.splitlines() if x.startswith("+") and not x.startswith("+++"))
        self.assertNotIn("BuildFingerprint=", added)
        self.assertNotIn("BuildId=", added)
        self.assertNotIn("BuildNumber=", added)

    def test_sensor_hal_and_product_switch_are_both_wired(self):
        apply = (ROOT / "patches/apply.sh").read_text()
        self.assertIn("apply_patch hardware/interfaces 0021-", apply)
        product = (ROOT / "patches/0008-virt-common-align-declared-hardware.patch").read_text()
        self.assertIn("device_virt_virt_common,motion_sensors_only,true", product)
        build = (ROOT / "build.sh").read_text()
        self.assertIn("sensors/aidl/default/include/sensors-impl/Sensors.h", build)
        self.assertIn("android.hardware.sensor.$sensor.xml", build)

    def test_ci_does_not_restore_stale_embedded_patches(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        self.assertNotIn("base64 --decode", workflow)
        self.assertIn('$(git rev-parse HEAD)" != "$GITHUB_SHA"', workflow)
        self.assertIn("git diff --quiet HEAD --", workflow)


if __name__ == "__main__":
    unittest.main()
