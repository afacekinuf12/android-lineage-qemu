#!/usr/bin/env python3
"""Stage one internally consistent VirtIO kernel build, retaining provenance."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stage(cache, source, report):
    cache, source = Path(cache).resolve(), Path(source).resolve()
    if cache == source or not (source / ".repo").is_dir():
        raise ValueError("Expected independent AOSP checkout")
    product = cache / "out/target/product/virtio_arm64only"
    objects = product / "obj/KERNEL_OBJ"
    release = (objects / "include/config/kernel.release").read_text().strip()
    if not re.fullmatch(r"6\.12\.[0-9]+-4k-[a-zA-Z0-9._+-]+", release):
        raise ValueError("Unexpected VirtIO kernel release: " + release)
    if (product / ".kernel_version.txt").read_text().strip() != release:
        raise ValueError("Product and kernel object versions differ")
    config = (objects / ".config").read_text()
    if "CONFIG_ARM64_4K_PAGES=y\n" not in config:
        raise ValueError("Kernel is not the selected ARM64 4 KB configuration")
    kernel = objects / "arch/arm64/boot/Image"
    with kernel.open("rb") as stream:
        header = stream.read(64)
    if header[56:60] != b"ARM\x64":
        raise ValueError("Invalid ARM64 Image header")
    modules = {}
    for path in sorted(objects.rglob("*.ko")):
        if path.name in modules:
            if digest(path) != digest(modules[path.name]):
                raise ValueError("Conflicting kernel module: " + path.name)
            continue
        metadata = subprocess.check_output(
            ["modinfo", "-F", "vermagic", str(path)], text=True).strip()
        if metadata.split()[0] != release:
            raise ValueError("Kernel ABI mismatch: " + path.name + ": " + metadata)
        modules[path.name] = path
    missing = {"btusb.ko", "cfg80211.ko", "virt_wifi.ko", "zram.ko", "zsmalloc.ko"} - modules.keys()
    if missing:
        raise ValueError("Missing kernel modules: " + ", ".join(sorted(missing)))
    target = source / "device/virt/kernel-virtio/6.12/arm64/4k"
    target.parent.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(
        ["git", "-C", str(cache / "kernel/virt/virtio"), "rev-parse", "HEAD"], text=True).strip()
    if not release.endswith("-g" + revision[:12]):
        raise ValueError("Kernel release and source revision differ")
    provenance = {
        "release": release, "source_revision": revision,
        "source_tree": str(cache), "config_sha256": digest(objects / ".config"),
        "files": {"kernel": digest(kernel), **{n: digest(p) for n, p in modules.items()}},
        "validation": "ARM64 Image header, 4 KB config and every module vermagic match",
        "runtime_validation": "pending",
    }
    if target.exists():
        existing = json.loads((target / "provenance.json").read_text())
        if existing != provenance or any(
                not (target / n).is_file() or digest(target / n) != checksum
                for n, checksum in provenance["files"].items()):
            raise ValueError("Existing staged kernel differs; retain it for diagnosis")
    else:
        temp = Path(tempfile.mkdtemp(prefix=".stage-", dir=target.parent))
        try:
            shutil.copy2(kernel, temp / "kernel")
            for name, path in modules.items():
                shutil.copy2(path, temp / name)
            (temp / ".kernel_version.txt").write_text(release + "\n")
            shutil.copy2(objects / ".config", temp / "kernel.config")
            (temp / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
            temp.rename(target)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
    Path(report).write_text(json.dumps(provenance, indent=2) + "\n")
    print("Staged {} and {} matching modules at {}".format(release, len(modules), target))


if __name__ == "__main__":
    try:
        stage(*sys.argv[1:])
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit("Kernel staging failed: " + str(exc))
