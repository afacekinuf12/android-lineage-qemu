#!/usr/bin/env python3
"""Apply the AOSP-specific patches to the Android 16 r4 upstream source files."""
import base64
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REVISION = "android-16.0.0_r4"
SERIES = (
    ("hardware/interfaces", "0021-sensors-limit-virtio-to-bridged-motion.patch",
     ("sensors/aidl/default/Android.bp", "sensors/aidl/default/include/sensors-impl/Sensors.h")),
    ("frameworks/base", "0022-uiautomator-include-test-base-dependency.patch",
     ("cmds/uiautomator/cmds/uiautomator/uiautomator.sh",)),
    ("system/core", "0024-aosp-init-virtio-boot-and-vendor-hook.patch",
     ("init/devices.cpp", "init/Android.bp")),
    ("build/soong", "0025-aosp-soong-allow-virtio-mesa-build.patch",
     ("ui/build/androidmk_denylist.go",)),
    ("external/gptfdisk", "0026-aosp-gptfdisk-recovery-variants.patch", ("Android.bp",)),
    ("bootable/recovery", "0027-aosp-recovery-keep-ethernet-up.patch",
     ("recovery_ui/ethernet_device.cpp",)),
)


def main():
    with tempfile.TemporaryDirectory(prefix="aosp-patches-") as temp:
        workspace = Path(temp)
        for project, patch, files in SERIES:
            checkout = workspace / project
            checkout.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q", str(checkout)], check=True)
            for relative in files:
                url = ("https://android.googlesource.com/platform/{}/+/refs/tags/{}/{}"
                       "?format=TEXT").format(project, REVISION, relative)
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = base64.b64decode(response.read(), validate=True)
                path = checkout / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            subprocess.run(["git", "-C", str(checkout), "apply", "--check",
                            str(ROOT / "patches" / patch)], check=True)
            subprocess.run(["git", "-C", str(checkout), "apply",
                            str(ROOT / "patches" / patch)], check=True)
            print("AOSP patch applies: " + patch, flush=True)
        subprocess.run([sys.executable, str(ROOT / "tests/check-motion-registration.py"),
                        str(workspace / "hardware/interfaces")], check=True)
        subprocess.run([sys.executable, str(ROOT / "tests/check-uiautomator-wrapper.py"),
                        str(workspace / "frameworks/base" / SERIES[1][2][0])], check=True)


if __name__ == "__main__":
    main()
