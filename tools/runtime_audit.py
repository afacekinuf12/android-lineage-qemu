#!/usr/bin/env python3
"""Read-only runtime consistency audit. This is not CTS or a device-trust verdict."""
import argparse
import collections
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

PROPS = (
    "ro.build.fingerprint", "ro.build.id", "ro.build.version.incremental",
    "ro.build.version.release", "ro.build.version.release_or_codename",
    "ro.build.type", "ro.build.tags", "ro.lineage.version",
    "ro.product.model", "ro.boot.verifiedbootstate", "ro.hardware.egl",
)
COMMANDS = {name: ["shell", "getprop", name] for name in PROPS}
COMMANDS.update({
    "mountinfo": ["shell", "cat", "/proc/self/mountinfo"],
    "sensors": ["shell", "dumpsys", "sensorservice"],
    "features": ["shell", "pm", "list", "features"],
    "graphics": ["shell", "dumpsys", "SurfaceFlinger"],
    "selinux": ["shell", "getenforce"],
    "adb_enabled": ["shell", "settings", "get", "global", "adb_enabled"],
    "development_enabled": ["shell", "settings", "get", "global", "development_settings_enabled"],
})
SENSOR_FEATURES = {
    "android.sensor.accelerometer": "android.hardware.sensor.accelerometer",
    "android.sensor.gyroscope": "android.hardware.sensor.gyroscope",
    "android.sensor.magnetic_field": "android.hardware.sensor.compass",
    "android.sensor.ambient_temperature": "android.hardware.sensor.ambient_temperature",
    "android.sensor.pressure": "android.hardware.sensor.barometer",
    "android.sensor.light": "android.hardware.sensor.light",
    "android.sensor.proximity": "android.hardware.sensor.proximity",
    "android.sensor.relative_humidity": "android.hardware.sensor.relative_humidity",
    "android.sensor.hinge_angle": "android.hardware.sensor.hinge_angle",
}
FP = re.compile(r"[^/:\s]+/[^/:\s]+/[^/:\s]+:([^/:\s]+)/([^/:\s]+)/([^/:\s]+):([^/:\s]+)/([^/:\s]+)")


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def collect(adb, serial, timeout):
    if not serial or serial.startswith("-"):
        raise ValueError("an explicit non-option ADB serial is required")
    deadline = time.monotonic() + timeout
    samples = {}
    for key, command in COMMANDS.items():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            samples[key] = {"status": "error", "detail": "overall deadline exceeded"}
            continue
        try:
            result = subprocess.run([adb, "-s", serial] + command, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=min(5, remaining), check=False)
            if result.returncode:
                samples[key] = {"status": "error", "detail": result.stderr.decode(errors="replace")[:200]}
            elif len(result.stdout) > 4 * 1024 * 1024:
                samples[key] = {"status": "error", "detail": "output exceeds 4 MiB"}
            else:
                samples[key] = {"status": "value", "value": result.stdout.decode(errors="replace").strip()}
        except subprocess.TimeoutExpired:
            samples[key] = {"status": "error", "detail": "command deadline exceeded"}
    return samples


def proc_mounts(text):
    """Parse mountinfo structurally; proc paths alone are not anomalous."""
    mounts = []
    for line in text.splitlines():
        parts = line.split()
        try:
            separator = parts.index("-")
            if separator < 6 or len(parts) < separator + 4:
                raise ValueError()
            int(parts[0]), int(parts[1])
            if not re.fullmatch(r"\d+:\d+", parts[2]):
                raise ValueError()
        except (ValueError, IndexError):
            raise ValueError("malformed mountinfo")
        path = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), parts[4])
        if path == "/proc" or path.startswith("/proc/"):
            mounts.append({"path": path, "root": parts[3],
                           "filesystem": parts[separator + 1], "options": parts[5].split(",")})
    if not any(m["path"] == "/proc" for m in mounts):
        raise ValueError("no /proc mount observed")
    return mounts


def analyze(samples):
    rows = []

    def read(key):
        sample = samples.get(key, {})
        if sample.get("status") != "value" or not sample.get("value"):
            return None
        return sample["value"]

    def add(key, state, detail, refs):
        rows.append({"id": key, "assessment": state, "detail": detail, "evidence_refs": refs})

    fingerprint = read("ro.build.fingerprint")
    match = FP.fullmatch(fingerprint or "")
    if not match:
        add("build.tuple", "inconclusive", "Fingerprint unavailable or malformed.", ["ro.build.fingerprint"])
    else:
        keys = ("ro.build.version.release_or_codename", "ro.build.id", "ro.build.version.incremental",
                "ro.build.type", "ro.build.tags")
        values = [read(k) for k in keys]
        if values[0] is None:
            values[0] = read("ro.build.version.release")
        refs = ["ro.build.fingerprint", *keys, "ro.build.version.release"]
        if any(v is None for v in values):
            add("build.tuple", "inconclusive", "Required build fields unavailable.", refs)
        else:
            mismatches = [{"property": k, "fingerprint_token": t, "value": v}
                          for k, t, v in zip(keys, match.groups(), values) if t != v]
            add("build.tuple", "different" if mismatches else "consistent",
                mismatches or "Fingerprint tokens match build fields; signing/authenticity unverified.", refs)

    for prop in ("ro.lineage.version", "ro.product.model", "ro.boot.verifiedbootstate",
                 "ro.hardware.egl", "selinux", "adb_enabled", "development_enabled"):
        value = read(prop)
        add(prop, "observed" if value else "inconclusive", value or "Unavailable; not a passing result.", [prop])

    graphics = read("graphics")
    lines = [line.strip() for line in (graphics or "").splitlines() if line.strip().startswith("GLES:")]
    if lines:
        renderer = lines[0]
        software = any(token in renderer.lower() for token in ("swiftshader", "llvmpipe", "softpipe"))
        add("graphics.renderer", "observed",
            {"surfaceflinger_gles": renderer, "software_backend_reported": software,
             "scope": "SurfaceFlinger context, not every app context or hardware proof."}, ["graphics"])
    else:
        add("graphics.renderer", "inconclusive", "No GLES renderer observation; EGL selector is insufficient.", ["graphics"])

    sensor_text, feature_text = read("sensors"), read("features")
    types = set(re.findall(r"\btype:\s*(android\.sensor\.[\w.]+)\(", sensor_text or ""))
    features = set(re.findall(r"^feature:([^=\s]+)", feature_text or "", re.M))
    if not types or not features:
        add("sensors.declarations", "inconclusive", "Sensor list or feature enumeration unavailable.", ["sensors", "features"])
    else:
        missing_features = [feature for sensor, feature in SENSOR_FEATURES.items()
                            if sensor in types and feature not in features]
        missing_sensors = [sensor for sensor, feature in SENSOR_FEATURES.items()
                           if feature in features and sensor not in types]
        add("sensors.declarations", "different" if missing_features or missing_sensors else "consistent",
            {"registered_types": sorted(types), "missing_features": sorted(missing_features),
             "missing_sensors": sorted(missing_sensors),
             "events": "not_tested"}, ["sensors", "features"])

    try:
        mounts = proc_mounts(read("mountinfo") or "")
        exact = [m for m in mounts if m["path"] in
                 ("/proc/cpuinfo", "/proc/meminfo", "/proc/sys/kernel/random/boot_id")]
        add("proc.mounts", "observed",
            {"mounts": mounts, "exact_file_mounts": exact,
             "scope": "ADB shell namespace; a separate mount is evidence to investigate, not proof of hiding."},
            ["mountinfo"])
    except ValueError as exc:
        add("proc.mounts", "inconclusive", str(exc), ["mountinfo"])

    errors = [key for key, sample in samples.items() if sample.get("status") == "error"]
    different = [row["id"] for row in rows if row["assessment"] == "different"]
    inconclusive = [row["id"] for row in rows if row["assessment"] == "inconclusive"]
    return {"schema_version": 1, "trust_verdict": "not_evaluated", "cts_verdict": "not_run",
            "source": "explicit_device_adb_shell",
            "consistency": "different" if different else "inconclusive" if errors or inconclusive else "consistent",
            "assessment_counts": dict(collections.Counter(row["assessment"] for row in rows)),
            "command_errors": errors, "findings": rows,
            "notes": ["No detection is not proof of physical-device fidelity.",
                      "No settings, permissions, properties or mounts were modified.",
                      "Raw device identifiers and complete dumps are not included."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--timeout", type=positive, default=40)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path, help="new JSON file; never overwrite evidence")
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.exists():
            raise ValueError("output already exists")
        adb = shutil.which(args.adb)
        if not adb:
            raise ValueError("ADB executable unavailable")
        report = analyze(collect(adb, args.serial, args.timeout))
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            for row in report["findings"]:
                print("{} {}: {}".format(row["assessment"].upper(), row["id"], row["detail"]))
            print("Consistency: {}; CTS not run; device trust not evaluated.".format(report["consistency"]))
        if report["command_errors"] or any(r["assessment"] == "inconclusive" for r in report["findings"]):
            return 2
        return 1 if report["consistency"] == "different" else 0
    except (OSError, ValueError) as exc:
        print("audit error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
