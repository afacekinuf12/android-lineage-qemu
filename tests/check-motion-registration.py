#!/usr/bin/env python3
"""Compile the patched registration block without Android dependencies."""

from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]) / "sensors/aidl/default"
header = (root / "include/sensors-impl/Sensors.h").read_text()
block = re.search(r"mHasWakeLock\(false\)\s*\{(.*?)\n    \}", header, re.S)
if not block:
    sys.exit("could not find Sensors constructor")
classes = sorted(set(re.findall(r"AddSensor<(\w+)>", block[1])))
source = """#include <iostream>
template<class T> void AddSensor() { std::cout << T::name() << "\\n"; }
"""
source += "\n".join(
    'struct %s { static const char* name() { return "%s"; } };' % (name, name)
    for name in classes)
source += "\nint main() {" + block[1] + "\n}\n"
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "register.cpp"
    path.write_text(source)
    for motion_only in (False, True):
        executable = Path(temp) / ("motion" if motion_only else "default")
        command = [os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Werror",
                   str(path), "-o", str(executable)]
        if motion_only:
            command.append("-DVIRTIO_MOTION_SENSORS_ONLY")
        subprocess.run(command, check=True, timeout=60)
        result = subprocess.run([str(executable)], check=True, capture_output=True,
                                text=True, timeout=5).stdout.splitlines()
        expected = (["AccelSensor", "GyroSensor", "MagnetometerSensor"] if motion_only else
                    ["AccelSensor", "GyroSensor", "AmbientTempSensor", "PressureSensor",
                     "MagnetometerSensor", "LightSensor", "ProximitySensor",
                     "RelativeHumiditySensor", "HingeAngleSensor"])
        if result != expected:
            sys.exit("unexpected registration set: " + repr(result))
        print("{} registration: {}".format("VirtIO" if motion_only else "Default", result))

bp = (root / "Android.bp").read_text()
for module in ("libsensorsexampleimpl", "android.hardware.sensors-service.example"):
    match = re.search(r'name: "' + re.escape(module) + r'",(.*?)(?=\n\})', bp, re.S)
    if not match or 'defaults: ["virt_motion_sensor_config"]' not in match[1]:
        sys.exit("missing consistent compile configuration for " + module)
print("Both constructor consumers use the same Soong configuration.")
