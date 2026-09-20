import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "aosp_product", ROOT / "scripts/verify-aosp-product.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class AospProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.fp = "VirtIO/virtio_aosp_arm64/virtio_arm64only:16/ACTUAL/20260917:user/dev-keys"
        self.write("build_fingerprint-virtio_aosp_arm64.txt", self.fp)
        for partition in ("system", "vendor", "product", "system_ext"):
            prefixes = ["ro." + partition + ".build"]
            if partition == "system":
                prefixes.append("ro.build")
            lines = []
            for prefix in prefixes:
                for suffix, value in {
                    ".fingerprint": self.fp, ".id": "ACTUAL",
                    ".version.incremental": "20260917", ".version.release": "16",
                    ".type": "user", ".tags": "dev-keys",
                }.items():
                    lines.append(prefix + suffix + "=" + value)
            self.write(partition + "/build.prop", "\n".join(lines))
        self.write("vendor/etc/permissions/motion.xml",
                   "<permissions>" + "".join('<feature name="{}"/>'.format(f)
                   for f in sorted(AUDIT.CONTRACT.SENSOR_FEATURES)) + "</permissions>")
        self.badging = {}
        for i, name in enumerate(sorted(AUDIT.REQUIRED_PACKAGES)):
            self.apk("system/app/Platform{}/app.apk".format(i), name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def archive(self, name, data=b""):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("classes.dex", data)
        return path

    def apk(self, path, name, payload=b"", extra=""):
        self.archive(path, payload)
        self.badging[path] = (name, "package: name='{}'\n{}".format(name, extra))

    def inspect(self, tool, path):
        return self.badging[str(path.relative_to(self.root))]

    def audit(self):
        return AUDIT.verify_staged(self.root, "aapt2", inspect=self.inspect)

    def test_consistent_aosp_stage_accepts_actual_build_tags(self):
        result = self.audit()
        self.assertTrue(result["accepted"], result["errors"])
        self.assertEqual("not_run", result["cts_verdict"])
        self.assertEqual("not_run", result["riskdetector_verdict"])

    def test_old_property_in_other_partition_rejected(self):
        for value in ("ro.lineage.version=23.2", "ro.build.description=LineageOS",
                      "ro.build.flavor=lineage_virtio_arm64only-user"):
            with self.subTest(value=value):
                p = self.root / "product/build.prop"
                original = p.read_text()
                p.write_text(original + "\n" + value)
                self.assertFalse(self.audit()["accepted"])
                p.write_text(original)

    def test_generic_filename_cannot_hide_package(self):
        self.apk("product/app/Browser/base.apk", "org.lineageos.jelly")
        self.assertTrue(any("APK dependency" in e for e in self.audit()["errors"]))

    def test_optional_sdk_dependency_rejected(self):
        self.apk("product/app/Neutral/base.apk", "example.neutral",
                 extra="uses-library-not-required:'org.lineageos.platform'")
        self.assertFalse(self.audit()["accepted"])

    def test_apk_dex_dependency_rejected(self):
        self.apk("product/app/Neutral/base.apk", "example.neutral",
                 payload=b"Llineageos/providers/LineageSettings;")
        self.assertTrue(any("APK DEX dependency" in e for e in self.audit()["errors"]))

    def test_framework_dex_dependency_rejected(self):
        self.archive("system/framework/services.jar", b"Lorg/lineageos/internal/Service;")
        self.assertTrue(any("DEX dependency" in e for e in self.audit()["errors"]))

    def test_marker_across_stream_chunks_detected(self):
        stream = io.BytesIO(b"a" * (1024 * 1024 - 4) + b"org.lineageos.platform")
        self.assertTrue(AUDIT.stream_has_dependency(stream))

    def test_feature_and_overlay_target_not_just_filenames(self):
        for xml in ('<permissions><feature name="org.lineageos.settings"/></permissions>',
                    '<manifest><overlay targetPackage="lineageos.platform"/></manifest>'):
            self.write("vendor/etc/permissions/neutral.xml", xml)
            self.assertFalse(self.audit()["accepted"])

    def test_missing_platform_provider_is_not_accepted(self):
        path = next(k for k, v in self.badging.items()
                    if v[0] == "com.android.providers.settings")
        (self.root / path).unlink()
        self.assertTrue(any("required platform package missing" in e for e in self.audit()["errors"]))

    def test_duplicate_package_rejected(self):
        self.apk("system_ext/app/SettingsCopy/base.apk", "com.android.settings")
        self.assertTrue(any("duplicate installed package" in e for e in self.audit()["errors"]))

    def test_invalid_xml_or_jar_never_passes(self):
        broken = self.write("product/etc/permissions/broken.xml", "<broken")
        with self.assertRaises(ET.ParseError):
            self.audit()
        broken.unlink()
        self.write("system/framework/services.jar", "not a zip")
        self.assertFalse(self.audit()["accepted"])

    def test_inspection_failure_is_not_zero_findings(self):
        def failed(tool, path):
            raise ValueError("tool failed")
        with self.assertRaises(ValueError):
            AUDIT.verify_staged(self.root, "aapt2", inspect=failed)

    def test_source_comments_are_not_runtime_dependencies(self):
        self.assertEqual([], list(AUDIT.dependency_lines(
            "// org.lineageos copyright\n/* vendor/lineage */\n# lineage-sdk\n")))
        self.assertTrue(list(AUDIT.dependency_lines(
            'libs: ["org.lineageos.platform.internal"],')))

    def test_missing_source_cannot_pass(self):
        self.assertFalse(AUDIT.verify_source(self.root)["accepted"])

    def test_source_gate_rejects_framework_dependency(self):
        self.write("frameworks/base/services/Android.bp",
                   'libs: ["org.lineageos.platform.internal"],')
        result = AUDIT.verify_source(self.root)
        self.assertIn("Lineage runtime dependency: frameworks/base/services/Android.bp",
                      result["errors"])


class AospBuildTests(unittest.TestCase):
    def test_overlay_condition_is_balanced_and_changes_installation(self):
        patch = (ROOT / "patches/0023-virt-common-scope-lineage-settings-overlay.patch").read_text()
        content = []
        for line in patch.splitlines():
            if line.startswith("+++"):
                continue
            if line.startswith(("+", " ")):
                content.append(line[1:])
        with tempfile.TemporaryDirectory() as temp:
            makefile = Path(temp) / "overlay.mk"
            makefile.write_text("\n".join(content) + "\nall:\n\t@echo $(PRODUCT_PACKAGES)\n")
            for distribution in ("", "virtio_arm64only"):
                result = subprocess.run(
                    ["make", "-s", "-f", str(makefile), "LINEAGE_BUILD=" + distribution],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("AodDefaultOnOverlay", result.stdout)
                self.assertEqual(bool(distribution),
                                 "LowPerformanceSettingsProviderOverlay" in result.stdout)

    def test_dispatch_and_missing_source_fail_before_host_changes(self):
        env = dict(os.environ, BUILD_FLAVOR="aosp", AOSP_SOURCE_ROOT=str(ROOT / "missing-tree"))
        p = subprocess.run(["bash", str(ROOT / "build.sh"), "--check"],
                           capture_output=True, text=True, env=env, timeout=5)
        self.assertEqual(2, p.returncode)
        self.assertIn("AOSP_SOURCE_ROOT", p.stderr)
        self.assertNotIn("sudo", p.stderr)

    def test_early_product_inheritance_uses_aosp_and_missing_keys_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inherited = root / "device/virt/virtio_arm64only/aosp_virtio_arm64only.mk"
            inherited.parent.mkdir(parents=True)
            inherited.write_text(
                "PRODUCT_PACKAGES += Settings SettingsProvider SystemUI\n"
                "SELECTED_KERNEL := device/virt/kernel-virtio/6.12/"
                "$(TARGET_PREBUILT_KERNEL_ARCH)/$(TARGET_PREBUILT_KERNEL_PAGE_SIZE)/kernel\n")
            harness = root / "test.mk"
            harness.write_text(
                "inherit-product = $(eval include $(1))\n"
                "include " + str(ROOT / "products/virtio_aosp/virtio_aosp_arm64.mk") + "\n"
                "all:\n\t@echo $(PRODUCT_NAME) $(PRODUCT_PACKAGES) $(SELECTED_KERNEL)\n")
            run = lambda **kw: subprocess.run(["make", "-s", "-f", str(harness)],
                cwd=root, capture_output=True, text=True, timeout=5, **kw)
            self.assertNotEqual(0, run().returncode)
            keys = root / "vendor/virtio_aosp/keys"
            keys.mkdir(parents=True)
            (keys / "releasekey.x509.pem").write_text("fixture")
            result = run()
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("virtio_aosp_arm64 Settings SettingsProvider SystemUI", result.stdout)
            self.assertIn("device/virt/kernel-virtio/6.12/arm64/4k/kernel", result.stdout)
            rejected = run(env=dict(os.environ, LINEAGE_BUILD="virtio_arm64only"))
            self.assertNotEqual(0, rejected.returncode)

    def test_incomplete_keys_do_not_write_android_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "android"
            (source / "build/make/target/product/security").mkdir(parents=True)
            store = root / "keys"
            store.mkdir()
            (store / "releasekey.pk8").write_bytes(b"incomplete")
            result = subprocess.run(["bash", str(ROOT / "scripts/prepare-aosp-keys.sh"),
                                     str(source)], capture_output=True, text=True,
                                    env=dict(os.environ, RELEASE_KEYS_DIR=str(store)), timeout=5)
            self.assertEqual(2, result.returncode)
            self.assertFalse((source / "vendor").exists())


if __name__ == "__main__":
    unittest.main()
