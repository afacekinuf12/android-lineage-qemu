import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("runtime_audit", ROOT / "tools/runtime_audit.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def fixture():
    values = {
        "ro.build.fingerprint": "test/vm/virt:16/BUILD/123:user/release-keys",
        "ro.build.id": "BUILD", "ro.build.version.incremental": "123",
        "ro.build.version.release": "16", "ro.build.version.release_or_codename": "16",
        "ro.build.type": "user", "ro.build.tags": "release-keys",
        "ro.lineage.version": "test-lineage", "ro.product.model": "virtual test device",
        "ro.boot.verifiedbootstate": "orange", "ro.hardware.egl": "angle",
        "selinux": "Enforcing", "adb_enabled": "1", "development_enabled": "1",
        "graphics": "GLES: Google, ANGLE (Mali-G715), SwiftShader driver, OpenGL ES 3.1",
        "mountinfo": "42 39 0:22 / /proc rw,relatime shared:4 - proc proc rw,gid=3009,hidepid=invisible",
        "sensors": "0x00000001) Accel Sensor | Vendor String | ver: 1 | type: android.sensor.accelerometer(1)\n",
        "features": "feature:android.hardware.sensor.accelerometer=0\n",
    }
    return {k: {"status": "value", "value": v} for k, v in values.items()}


def finding(report, name):
    return next(r for r in report["findings"] if r["id"] == name)


class RuntimeAuditTests(unittest.TestCase):
    def test_truthful_vm_is_not_a_trust_failure(self):
        result = AUDIT.analyze(fixture())
        self.assertEqual("consistent", result["consistency"])
        self.assertEqual("not_evaluated", result["trust_verdict"])
        self.assertEqual("not_run", result["cts_verdict"])
        self.assertEqual("observed", finding(result, "ro.boot.verifiedbootstate")["assessment"])

    def test_original_stageb_tuple_is_rejected(self):
        data = fixture()
        data["ro.build.fingerprint"]["value"] = "google/caiman/caiman:16/BP4A.260205.001/13561507:user/release-keys"
        data["ro.build.id"]["value"] = "BP4A.251205.006"
        data["ro.build.version.incremental"]["value"] = "20260908"
        result = finding(AUDIT.analyze(data), "build.tuple")
        self.assertEqual("different", result["assessment"])
        self.assertEqual(2, len(result["detail"]))

    def test_empty_or_error_property_cannot_pass(self):
        for sample in ({"status": "error"}, {"status": "value", "value": ""}):
            data = fixture()
            data["ro.build.id"] = sample
            self.assertEqual("inconclusive", finding(AUDIT.analyze(data), "build.tuple")["assessment"])

    def test_all_failed_reads_are_inconclusive(self):
        result = AUDIT.analyze({k: {"status": "error"} for k in AUDIT.COMMANDS})
        self.assertEqual("inconclusive", result["consistency"])
        self.assertTrue(result["command_errors"])
        self.assertFalse(any(r["assessment"] == "consistent" for r in result["findings"]))

    def test_malformed_fingerprint_is_inconclusive(self):
        data = fixture()
        data["ro.build.fingerprint"]["value"] = "unknown"
        self.assertEqual("inconclusive", finding(AUDIT.analyze(data), "build.tuple")["assessment"])

    def test_renderer_uses_actual_gles_line_not_selector(self):
        result = finding(AUDIT.analyze(fixture()), "graphics.renderer")
        self.assertTrue(result["detail"]["software_backend_reported"])
        data = fixture()
        data["graphics"] = {"status": "error"}
        self.assertEqual("inconclusive", finding(AUDIT.analyze(data), "graphics.renderer")["assessment"])

    def test_sensor_count_is_not_a_fidelity_pass(self):
        data = fixture()
        data["sensors"]["value"] += "0x2) type: android.sensor.pressure(6)\n"
        result = finding(AUDIT.analyze(data), "sensors.declarations")
        self.assertEqual("different", result["assessment"])
        self.assertEqual(["android.hardware.sensor.barometer"], result["detail"]["missing_features"])
        self.assertEqual("not_tested", result["detail"]["events"])

    def test_declared_sensor_must_be_registered(self):
        data = fixture()
        data["features"]["value"] += "feature:android.hardware.sensor.gyroscope\n"
        result = finding(AUDIT.analyze(data), "sensors.declarations")
        self.assertEqual(["android.sensor.gyroscope"], result["detail"]["missing_sensors"])

    def test_unavailable_sensor_dump_not_zero_sensors(self):
        data = fixture()
        data["sensors"]["value"] = "Permission Denial"
        self.assertEqual("inconclusive", finding(AUDIT.analyze(data), "sensors.declarations")["assessment"])

    def test_procfs_paths_are_not_hidden_mount_proof(self):
        result = finding(AUDIT.analyze(fixture()), "proc.mounts")
        self.assertEqual("observed", result["assessment"])
        self.assertEqual([], result["detail"]["exact_file_mounts"])
        self.assertEqual("proc", result["detail"]["mounts"][0]["filesystem"])

    def test_exact_proc_file_mount_is_preserved_as_evidence(self):
        data = fixture()
        data["mountinfo"]["value"] += "\n90 42 0:24 /file /proc/cpuinfo ro - tmpfs tmpfs rw"
        result = finding(AUDIT.analyze(data), "proc.mounts")
        self.assertEqual("observed", result["assessment"])
        self.assertEqual("/proc/cpuinfo", result["detail"]["exact_file_mounts"][0]["path"])

    def test_malformed_mountinfo_cannot_pass(self):
        for text in ("", "not a mount table", "a b c / /proc rw - proc proc rw"):
            with self.assertRaises(ValueError):
                AUDIT.proc_mounts(text)

    def test_serial_required_and_scoped_on_every_call(self):
        with patch.object(AUDIT.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"1", b"")) as run:
            AUDIT.collect("adb", "test-serial", 20)
        for call in run.call_args_list:
            self.assertEqual(["adb", "-s", "test-serial"], call.args[0][:3])
            self.assertLessEqual(call.kwargs["timeout"], 5)
        with self.assertRaises(ValueError):
            AUDIT.collect("adb", "-invalid", 20)
        with self.assertRaises(SystemExit):
            AUDIT.main([])

    def test_total_deadline_includes_stalled_commands(self):
        now = [0]

        def stalled(*args, timeout, **kwargs):
            now[0] += timeout
            raise subprocess.TimeoutExpired(args, timeout)

        with patch.object(AUDIT.time, "monotonic", side_effect=lambda: now[0]), \
                patch.object(AUDIT.subprocess, "run", side_effect=stalled) as run:
            samples = AUDIT.collect("adb", "serial", 2)
        self.assertEqual(1, run.call_count)
        self.assertEqual(2, now[0])
        self.assertTrue(all(s["status"] == "error" for s in samples.values()))

    def test_sensitive_raw_dumps_are_not_exported(self):
        data = fixture()
        data["graphics"]["value"] += "\nprivate-other-log"
        data["sensors"]["value"] += "\nprivate-user-package"
        text = str(AUDIT.analyze(data))
        self.assertNotIn("private-other-log", text)
        self.assertNotIn("private-user-package", text)


if __name__ == "__main__":
    unittest.main()
