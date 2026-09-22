#!/usr/bin/env python3
"""Exercise the real Make property rule when generated metadata changes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

source = Path(sys.argv[1]).read_text()
start = source.index("define build-properties\n")
end = source.index("\nendef", start) + len("\nendef")
rule = source[start:end]
with tempfile.TemporaryDirectory(prefix="aosp-sysprop-") as temp:
    root = Path(temp)
    values = {
        "fingerprint": "VirtIO/product/device:16/BUILD/day1:user/dev-keys",
        "number": "day1",
        "datetime": "1000",
    }
    for name, value in values.items():
        (root / name).write_text(value + "\n")
    harness = root / "rules.mk"
    harness.write_text(
        "TARGET_PRODUCT := virtio_aosp_arm64\n"
        "BUILD_FINGERPRINT_FILE := fingerprint\n"
        "BUILD_NUMBER_FILE := number\n"
        "BUILD_DATETIME_FILE := datetime\n"
        "POST_PROCESS_PROPS := /usr/bin/true\n"
        "PLATFORM_SDK_VERSION := 36\n"
        "generate-common-build-props = cat fingerprint number datetime >> $(2)\n"
        + rule + "\n$(eval $(call build-properties,vendor,vendor.prop,,,,,))\n"
    )
    output = root / "vendor.prop"

    def make():
        subprocess.run(["make", "-s", "-f", str(harness), "vendor.prop"],
                       cwd=root, check=True, stdout=subprocess.DEVNULL)

    make()
    for name in values:
        old = output.read_text()
        anchor = time.time()
        for item in values:
            os.utime(root / item, (anchor - 20, anchor - 20))
        os.utime(output, (anchor - 10, anchor - 10))
        values[name] += "-updated"
        (root / name).write_text(values[name] + "\n")
        # Only the changed input is newer, so each dependency is exercised.
        os.utime(root / name, (anchor - 5, anchor - 5))
        make()
        current = output.read_text()
        assert current != old, "property output was not rebuilt for " + name
        assert all(value in current for value in values.values())
    print("AOSP Make metadata dependencies: fingerprint, number and datetime passed")
