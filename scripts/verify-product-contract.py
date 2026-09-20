#!/usr/bin/env python3
"""Validate staged build metadata and the VirtIO motion-sensor declaration set."""

import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

PARTITIONS = ("system", "vendor", "product", "system_ext", "odm",
              "system_dlkm", "vendor_dlkm", "odm_dlkm")
SENSOR_FEATURES = {
    "android.hardware.sensor.accelerometer",
    "android.hardware.sensor.gyroscope",
    "android.hardware.sensor.compass",
}
FINGERPRINT = re.compile(
    r"(?P<brand>[^/:\s]+)/(?P<product>[^/:\s]+)/(?P<device>[^/:\s]+):"
    r"(?P<release>[^/:\s]+)/(?P<id>[^/:\s]+)/(?P<incremental>[^/:\s]+):"
    r"(?P<type>[^/:\s]+)/(?P<tags>[^/:\s]+)"
)


def properties(path):
    result = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("import "):
            raise ValueError("{}:{}: imported properties are not supported".format(path, number))
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not key or key.endswith("?"):
            raise ValueError("{}:{}: expected finalized key=value".format(path, number))
        if key in result and result[key] != value:
            raise ValueError("{}:{}: conflicting property {}".format(path, number, key))
        result[key] = value
    return result


def verify(root, target="lineage_virtio_arm64only"):
    root = Path(root)
    if not re.fullmatch(r"[a-zA-Z0-9_]+", target):
        raise ValueError("invalid build target")
    canonical_file = root / ("build_fingerprint-" + target + ".txt")
    canonical = canonical_file.read_text(encoding="utf-8").strip()
    if not FINGERPRINT.fullmatch(canonical):
        raise ValueError("invalid generated build fingerprint: " + str(canonical_file))
    errors, checked = [], []
    global_tuples = []
    for partition in PARTITIONS:
        candidates = (root / partition / "build.prop", root / partition / "etc/build.prop")
        paths = [path for path in candidates if path.is_file()]
        if not paths and (partition in ("system", "vendor") or (root / partition).is_dir()):
            errors.append(partition + ": staged build.prop missing")
        for path in paths:
            props = properties(path)
            prefixes = ["ro." + partition + ".build"]
            if partition == "system" or "ro.build.fingerprint" in props:
                prefixes.append("ro.build")
            for prefix in prefixes:
                label = str(path.relative_to(root)) + ":" + prefix
                fp = props.get(prefix + ".fingerprint", "")
                match = FINGERPRINT.fullmatch(fp)
                if not match:
                    errors.append(label + ": missing or malformed fingerprint")
                    continue
                if fp != canonical:
                    errors.append(label + ": does not match generated build fingerprint")
                for token, suffix in (("id", ".id"), ("incremental", ".version.incremental"),
                                      ("type", ".type"), ("tags", ".tags")):
                    key = prefix + suffix
                    if props.get(key) != match[token]:
                        errors.append(label + ": fingerprint token differs from " + key)
                # Preview fingerprints may use a codename rather than last stable release.
                release = props.get(prefix + ".version.release_or_codename",
                                    props.get(prefix + ".version.release"))
                if release != match["release"]:
                    errors.append(label + ": fingerprint release/codename differs")
                if prefix == "ro.build":
                    global_tuples.append((props.get("ro.build.id"),
                                          props.get("ro.build.version.incremental"),
                                          props.get("ro.build.version.security_patch")))
                checked.append(label)
    if len(set(global_tuples)) > 1:
        errors.append("global build ID/incremental/security patch differs across partitions")

    declared, removed = set(), set()
    for partition in PARTITIONS:
        for directory in ("etc/permissions", "etc/sysconfig"):
            for path in sorted((root / partition / directory).glob("*.xml")):
                tree = ET.parse(path)
                for node in tree.getroot():
                    name = node.get("name", "")
                    if name.startswith("android.hardware.sensor."):
                        if node.tag == "feature":
                            declared.add(name)
                        elif node.tag == "unavailable-feature":
                            removed.add(name)
    for feature in sorted(SENSOR_FEATURES - (declared - removed)):
        errors.append("missing motion feature: " + feature)
    # A stale declaration must not be concealed with unavailable-feature.
    for feature in sorted(declared - SENSOR_FEATURES):
        errors.append("sensor outside the VirtIO motion profile: " + feature)
    return {"accepted": not errors, "checked_builds": checked,
            "sensor_features": sorted(declared - removed), "errors": errors,
            "scope": "staged metadata and XML only; HAL runtime/events not evaluated"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product_out", type=Path)
    parser.add_argument("--target", default="lineage_virtio_arm64only")
    args = parser.parse_args()
    try:
        result = verify(args.product_out, args.target)
    except (OSError, ValueError, ET.ParseError) as exc:
        print("product contract error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
