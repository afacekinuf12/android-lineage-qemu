#!/usr/bin/env python3
"""Compile the patched vendor hooks and check their placement in AOSP init."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]) / "init"
properties = (root / "property_service.cpp").read_text()
defaults = properties[properties.index("void PropertyLoadBootDefaults() {"):
                      properties.index("void PropertyLoadDerivedDefaults() {")]
assert defaults.index("PropertySetNoSocket(name, value") < defaults.index("vendor_load_properties();")
assert defaults.index("vendor_load_properties();") < defaults.index("property_derive_build_fingerprint();")
init = properties[properties.index("void PropertyInit() {"):properties.index("static void HandleInitSocket()")]
assert init.index("ProcessKernelCmdline();") < init.index("vendor_process_bootenv();")
assert init.index("vendor_process_bootenv();") < init.index("ExportKernelBootProps();")
bp = (root / "Android.bp").read_text()
assert 'init_device_sources + ["vendor_init.cpp"]' in bp
assert 'select(soong_config_variable("libinit", "vendor_init_lib")' in bp

with tempfile.TemporaryDirectory(prefix="vendor-init-hooks-") as temp:
    work = Path(temp)
    main = work / "main.cpp"
    main.write_text('''#include "vendor_init.h"
int called = 0;
int main() {
    vendor_process_bootenv();
    vendor_load_properties();
#ifdef DEVICE_HOOKS
    return called != 3;
#else
    return called != 0;
#endif
}
''')
    device = work / "device.cpp"
    device.write_text('''#include "vendor_init.h"
extern int called;
void vendor_process_bootenv() { called |= 1; }
void vendor_load_properties() { called |= 2; }
''')
    for enabled in (False, True):
        executable = work / ("device" if enabled else "default")
        command = [os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Werror",
                   "-I" + str(root), str(main), str(root / "vendor_init.cpp")]
        if enabled:
            command.extend(["-DDEVICE_HOOKS", str(device)])
        command.extend(["-o", str(executable)])
        subprocess.run(command, check=True, timeout=60)
        subprocess.run([str(executable)], check=True, timeout=5)
        print("Vendor hook compile/link/run: " + ("device overrides" if enabled else "default no-ops"))
print("Boot environment and property hooks run before derived values.")
