#!/usr/bin/env python3
"""Read-only inventory of known Android build caches on the selected runner."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def git_revision(path):
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(path),
                             "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else None


def main():
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    home_dir = Path.home()
    candidates = [
        workspace / "android/lineage", workspace / "android/aosp",
        workspace / "android/aosp16", home_dir / "aosp", home_dir / "android/aosp",
        home_dir / "android/lineage",
    ]
    report = {
        "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "python": sys.version,
        "tools": {name: shutil.which(name) for name in
                  ("python3", "git", "repo", "qemu-img", "ninja", "make", "java", "ccache")},
        "workspace": str(workspace), "filesystems": {}, "source_trees": [],
    }
    report["python_candidates"] = {
        str(p): p.is_file() for p in (
            home_dir / "miniconda3/bin/python3",
            workspace / ".build-python/bin/python3",
        )
    }
    for path in (workspace, home_dir, Path("/data00")):
        if path.is_dir():
            usage = shutil.disk_usage(path)
            report["filesystems"][str(path)] = {
                "total_gib": round(usage.total / 2**30, 1),
                "free_gib": round(usage.free / 2**30, 1),
            }
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        report["memory"] = [line for line in meminfo.read_text().splitlines()
                            if line.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:"))]
    for path in candidates:
        if not (path / ".repo").is_dir():
            continue
        entry = {
            "path": str(path), "envsetup": (path / "build/envsetup.sh").is_file(),
            "lineage_product_present": (path / "vendor/lineage").is_dir(),
            "framework_revision": git_revision(path / "frameworks/base"),
            "repo_tool": str(path / ".repo/repo/repo"),
        }
        for key, directory in (
            ("kernel_artifacts", path / "out/target/product/virtio_arm64only/kernel-virtio"),
            ("kernel_prebuilts", path / "device/virt/kernel-virtio"),
        ):
            entry[key] = [str(p.relative_to(path)) for p in directory.glob("**/kernel")
                          if p.is_file()]
        out = path / "out/target/product/virtio_arm64only"
        entry["previous_product_files"] = {
            name: (out / name).is_file()
            for name in ("kernel", ".kernel_version.txt", "boot.img", "vendor_boot.img")
        }
        entry["kernel_objects"] = [
            {"path": str(p.relative_to(path)), "bytes": p.stat().st_size}
            for pattern in ("**/Image", "**/Image.gz", "**/*.ko", ".config")
            for p in (out / "obj/KERNEL_OBJ").glob(pattern) if p.is_file()
        ]
        entry["kernel_source"] = git_revision(path / "kernel/virt/virtio")
        entry["kernel_version"] = (
            (out / ".kernel_version.txt").read_text() if
            (out / ".kernel_version.txt").is_file() else None)
        entry["kernel_config"] = (
            (out / "obj/KERNEL_OBJ/.config").read_text() if
            (out / "obj/KERNEL_OBJ/.config").is_file() else None)
        entry["release_configs"] = [
            str(p.relative_to(path)) for p in
            (path / "build/release/release_configs").glob("*.textproto")
        ]
        report["source_trees"].append(entry)
    keys = home_dir / ".android-lineage-qemu-release-keys"
    report["signing_pairs_present"] = {
        name: all((keys / (name + suffix)).is_file() for suffix in (".pk8", ".x509.pem"))
        for name in ("releasekey", "platform", "shared", "media", "networkstack",
                     "sdk_sandbox", "bluetooth", "nfc")
    }
    output = json.dumps(report, indent=2) + "\n"
    Path(sys.argv[1]).write_text(output)
    print(output)


if __name__ == "__main__":
    main()
