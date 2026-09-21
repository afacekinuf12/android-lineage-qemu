#!/usr/bin/env python3
"""Check AOSP product dependencies and installed distribution components.

This is a build contract, not a device-trust verdict or a RiskDetector emulator.
Source comments and licensing attribution are not runtime components.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

SPEC = importlib.util.spec_from_file_location(
    "product_contract", Path(__file__).with_name("verify-product-contract.py"))
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)

MARKER = re.compile(r"org[./]lineageos|(?:^|[^a-z])lineageos[./]|"
                    r"ro\.lineage\.|lineage-sdk|vendor/lineage|"
                    r"lineage_virtio", re.I)
CORE_ROOTS = (
    "frameworks/base", "packages/apps/Settings", "packages/apps/Launcher3",
    "packages/apps/Provision", "system/core", "system/sepolicy",
)
CORE_SUFFIXES = {".java", ".kt", ".bp", ".mk", ".aidl", ".cpp", ".h", ".xml", ".te"}
REQUIRED_PACKAGES = {
    "com.android.settings", "com.android.systemui", "com.android.providers.settings",
    "com.android.launcher3", "com.android.provision",
}
BYTE_MARKERS = (
    b"org.lineageos", b"org/lineageos", b"Llineageos/", b"lineageos.platform",
)
SUPPORT_MANIFEST = Path(__file__).resolve().parents[1] / "products/virtio_aosp/local_manifest.xml"
# These two source repositories are replaced by the validated prebuilt kernel.
PREBUILT_KERNEL_DEPENDENCIES = {
    ("kernel/mainline/configs", "android_kernel_mainline_configs"),
    ("kernel/virt/virtio", "android_kernel_virt_virtio"),
}


def support_dependency_errors(root, manifest=SUPPORT_MANIFEST):
    projects = {p.attrib["path"]: p.attrib["name"]
                for p in ET.parse(manifest).getroot().findall("project")}
    errors = []
    for relative in projects:
        project = root / relative
        if not (project / ".git").exists():
            errors.append("missing device support checkout: " + relative)
        dependencies = project / "lineage.dependencies"
        if not dependencies.is_file():
            continue
        entries = json.loads(dependencies.read_text())
        if not isinstance(entries, list):
            raise ValueError("Invalid dependency list: " + str(dependencies))
        for entry in entries:
            if not isinstance(entry, dict) or not all(
                    isinstance(entry.get(key), str) for key in ("target_path", "repository")):
                raise ValueError("Invalid dependency entry: " + str(dependencies))
            target, repository = entry["target_path"], entry["repository"]
            if (target, repository) in PREBUILT_KERNEL_DEPENDENCIES:
                continue
            if projects.get(target) != repository:
                errors.append("device dependency absent from support manifest: {} -> {}".format(
                    relative, target))
    return errors


def dependency_lines(text):
    """Ignore comments; retain runtime strings, imports and build dependencies."""
    text = re.sub(r"/\*.*?\*/|<!--.*?-->", "", text, flags=re.S)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//", "*")):
            continue
        if MARKER.search(line):
            yield line


def verify_source(root):
    root = Path(root).resolve()
    errors = support_dependency_errors(root)
    required = ("build/envsetup.sh", "build/soong/soong_ui.bash",
                "device/virt/virtio_arm64only/aosp_virtio_arm64only.mk",
                "device/virt/virtio-common/device-common.mk",
                "device/virt/virt-common/virt-common.mk",
                "device/mainline/common/mainline_common.mk",
                "hardware/mainline/common/Android.bp",
                "external/libdisplay-info-upstream/Android.bp",
                "prebuilts/mesa-build-dep/bin/meson",
                "hardware/interfaces/sensors/aidl/default/Android.bp",
                "frameworks/base/packages/SettingsProvider/Android.bp",
                "frameworks/base/packages/SystemUI/Android.bp",
                "device/virt/virtio_arm64/vm_templates/utm/config.plist",
                "device/virt/virtio_arm64/bootmgr/grub/prebuilt/boot/BOOTAA64.EFI")
    for relative in required:
        if not (root / relative).is_file():
            errors.append("missing source: " + relative)
    for relative in ("vendor/lineage", "lineage-sdk", "device/lineage"):
        if (root / relative).exists():
            errors.append("distribution source tree remains: " + relative)
    if (root / "kernel/virt/virtio/Makefile").exists():
        errors.append("source-built VirtIO kernel still requires a separate build integration; "
                      "use a validated prebuilt kernel/modules set for this AOSP profile")
    if not any((root / "device/virt/kernel-virtio").glob("6.12/arm64/**/kernel")):
        errors.append("missing VirtIO 6.12 ARM64 prebuilt kernel/modules; see AOSP_PRODUCT.md")
    checked = 0
    for relative in CORE_ROOTS:
        directory = root / relative
        if not directory.is_dir():
            errors.append("missing platform component: " + relative)
            continue
        if not (directory / "Android.bp").is_file():
            errors.append("missing platform build definition: " + relative + "/Android.bp")
        for path in sorted(directory.rglob("*")):
            if path.suffix not in CORE_SUFFIXES or not path.is_file():
                continue
            checked += 1
            if next(dependency_lines(path.read_text(errors="replace")), None):
                errors.append("Lineage runtime dependency: " + str(path.relative_to(root)))
    return {"accepted": not errors, "errors": errors, "checked_source_files": checked,
            "scope": "platform dependency preflight; not a complete Android compile"}


def inspect_apk(aapt2, path):
    p = subprocess.run([aapt2, "dump", "badging", str(path)],
                       capture_output=True, timeout=30, check=False)
    if p.returncode:
        raise ValueError("cannot inspect APK: " + path.name)
    text = p.stdout.decode(errors="replace")
    match = re.search(r"^package: name='([^']+)'", text, re.M)
    if not match:
        raise ValueError("APK package identity unavailable: " + path.name)
    manifest = subprocess.run(
        [aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", str(path)],
        capture_output=True, timeout=30, check=False)
    if manifest.returncode:
        raise ValueError("cannot inspect APK manifest: " + path.name)
    return match[1], text + "\n" + manifest.stdout.decode(errors="replace")


def stream_has_dependency(stream):
    tail = b""
    while True:
        block = stream.read(1024 * 1024)
        if not block:
            return False
        combined = tail + block
        if any(marker in combined for marker in BYTE_MARKERS):
            return True
        tail = combined[-64:]


def jar_has_dependency(path):
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.filename.endswith((".dex", ".class")):
                with archive.open(info) as stream:
                    if stream_has_dependency(stream):
                        return True
    return False


def verify_staged(root, aapt2, inspect=inspect_apk):
    root = Path(root).resolve()
    contract = CONTRACT.verify(root, "virtio_aosp_arm64")
    errors = list(contract["errors"])
    packages, checked_apks, checked_jars = {}, 0, 0
    for partition in CONTRACT.PARTITIONS:
        for path in sorted((root / partition).rglob("*")):
            if not path.is_file():
                continue
            relative = str(path.relative_to(root))
            # Include symlinked installed artifacts only when their content is
            # still in the selected staging tree.
            try:
                path.resolve().relative_to(root)
            except ValueError:
                errors.append("installed file escapes staging: " + relative)
                continue
            if "lineage" in relative.lower():
                errors.append("distribution artifact remains: " + relative)
            if path.name == "build.prop" or path.suffix == ".prop":
                props = CONTRACT.properties(path)
                for key, value in props.items():
                    if "lineage" in (key + "=" + value).lower():
                        errors.append("distribution property: " + relative + ":" + key)
            elif path.suffix == ".xml":
                try:
                    tree = ET.parse(path)
                except ET.ParseError:
                    errors.append("cannot parse installed XML: " + relative)
                    continue
                for node in tree.iter():
                    if MARKER.search(" ".join(node.attrib.values()) + " " + (node.text or "")):
                        errors.append("distribution XML dependency: " + relative)
                        break
            elif path.suffix == ".rc":
                if next(dependency_lines(path.read_text(errors="replace")), None):
                    errors.append("distribution init dependency: " + relative)
            elif path.suffix == ".apk":
                name, badging = inspect(aapt2, path)
                checked_apks += 1
                packages.setdefault(name, []).append(relative)
                if MARKER.search(name) or MARKER.search(badging):
                    errors.append("distribution APK dependency: " + relative + ":" + name)
                try:
                    if jar_has_dependency(path):
                        errors.append("distribution APK DEX dependency: " + relative)
                except zipfile.BadZipFile:
                    errors.append("cannot inspect APK DEX: " + relative)
            elif path.suffix == ".jar":
                checked_jars += 1
                try:
                    if jar_has_dependency(path):
                        errors.append("distribution DEX dependency: " + relative)
                except zipfile.BadZipFile:
                    errors.append("cannot inspect framework JAR: " + relative)
    for package in sorted(REQUIRED_PACKAGES - packages.keys()):
        errors.append("required platform package missing: " + package)
    for package, paths in packages.items():
        if len(paths) > 1:
            errors.append("duplicate installed package: " + package)
    return {"accepted": not errors, "errors": errors,
            "checked_apks": checked_apks, "checked_jars": checked_jars,
            "packages": sorted(packages),
            "scope": "staged properties, XML, APK metadata and APK/JAR DEX; "
                     "source preflight and runtime validation are also required",
            "cts_verdict": "not_run", "riskdetector_verdict": "not_run"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-root", type=Path)
    group.add_argument("--product-out", type=Path)
    parser.add_argument("--aapt2")
    args = parser.parse_args(argv)
    if args.product_out and not args.aapt2:
        parser.error("--product-out requires --aapt2")
    try:
        result = (verify_source(args.source_root) if args.source_root
                  else verify_staged(args.product_out, args.aapt2))
    except (OSError, ValueError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        print("AOSP contract error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
