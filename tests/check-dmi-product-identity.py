#!/usr/bin/env python3
"""Compile the real DMI property loader and exercise both product configurations."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

library = Path(sys.argv[1]) / "libraries/libinit"
with tempfile.TemporaryDirectory(prefix="dmi-product-identity-") as temp:
    work = Path(temp)
    (work / "android-base").mkdir()
    (work / "android-base/file.h").write_text(
        '#include <string>\nnamespace android::base {\n'
        'inline bool ReadFileToString(const std::string&, std::string*) { return false; }\n'
        '}\n')
    main = work / "main.cpp"
    main.write_text(r'''
#include <libinit_set_properties.h>
#include <libinit_utils.h>
#include <cassert>
#include <map>
#include <string>

static std::map<std::string, std::string> properties = {
    {"brand", "VirtIO"}, {"model", "VirtIO ARM64"}, {"manufacturer", "VirtIO"},
};
static const std::map<std::string, std::string> dmi = {
    {"bios_version", "QEMU firmware"},
    {"product_serial", "sample-serial"},
    {"chassis_vendor", "QEMU"},
    {"product_name", "QEMU Virtual Machine"},
    {"sys_vendor", "QEMU"},
};
static std::string read_dmi(const std::string& path) {
    const std::string prefix = "/sys/devices/virtual/dmi/id/";
    assert(path.substr(0, prefix.size()) == prefix);
    return dmi.at(path.substr(prefix.size()));
}
void set_prop_from_file(const std::string& prop, const std::string& path) {
    properties[prop] = read_dmi(path);
}
void set_ro_build_prop(const std::string& prop, const std::string& value, bool product) {
    assert(product);
    properties[prop] = value;
}
void set_ro_build_prop_from_file(const std::string& prop, const std::string& path,
                                 bool product) {
    set_ro_build_prop(prop, read_dmi(path), product);
}
int main() {
    set_properties_from_dmi_id();
    assert(properties.at("ro.bootloader") == "QEMU firmware");
    assert(properties.at("ro.serialno") == "sample-serial");
#ifdef PRESERVE_DMI_PRODUCT_IDENTITY
    assert(properties.at("brand") == "VirtIO");
    assert(properties.at("model") == "VirtIO ARM64");
    assert(properties.at("manufacturer") == "VirtIO");
#else
    assert(properties.at("brand") == "QEMU");
    assert(properties.at("model") == "QEMU Virtual Machine");
    assert(properties.at("manufacturer") == "QEMU");
#endif
    assert(properties.size() == 5);
}
''')
    for preserve in (False, True):
        executable = work / ("selected-product" if preserve else "upstream-dmi")
        command = [
            os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Werror",
            "-I" + str(work), "-I" + str(library / "include"),
            str(library / "libinit_set_properties.cpp"), str(main), "-o", str(executable),
        ]
        if preserve:
            command.append("-DPRESERVE_DMI_PRODUCT_IDENTITY")
        subprocess.run(command, check=True, timeout=60)
        subprocess.run([str(executable)], check=True, timeout=5)
        print("DMI loader compile/run passed: " + executable.name)
