#!/usr/bin/env python3
"""Create an isolated output or resume a recorded output of the same AOSP tree."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

MARKER = "aosp-output-identity.json"


def identity(source, release, manifest):
    return {
        "source_root": str(Path(source).resolve()),
        "product": "virtio_aosp_arm64",
        "variant": "user",
        "release": release,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
    }


def select_output(source, release, manifest, resume=None):
    source = Path(source).resolve()
    parent = source / "out"
    if parent.is_symlink():
        raise ValueError("AOSP out must not be a symlink")
    expected = identity(source, release, manifest)
    if resume:
        output = Path(resume).absolute()
        if (output.parent != parent or output.is_symlink() or
                not re.fullmatch(r"virtio-aosp\.[A-Za-z0-9_-]+", output.name)):
            raise ValueError("Resume requires an isolated output directly inside this AOSP tree")
        marker = output / MARKER
        if marker.is_symlink() or not marker.is_file():
            raise ValueError("Resume requires an existing AOSP output identity")
        if json.loads(marker.read_text()) != expected:
            raise ValueError("Resume identity differs: source, product, variant, release or manifest")
        recorded = output / "resolved-manifest.xml"
        if recorded.is_symlink() or recorded.read_bytes() != manifest:
            raise ValueError("Recorded source manifest differs from the selected checkout")
    else:
        parent.mkdir(exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix="virtio-aosp.", dir=parent))
        (output / MARKER).write_text(json.dumps(expected, indent=2) + "\n")
        (output / "resolved-manifest.xml").write_bytes(manifest)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aosp-output-manifest-") as temp:
        manifest = Path(temp) / "manifest.xml"
        subprocess.run(["repo", "manifest", "-r", "-o", str(manifest)],
                       cwd=args.source, check=True, stdout=subprocess.DEVNULL)
        output = select_output(args.source, args.release, manifest.read_bytes(), args.resume)
    print(output)


if __name__ == "__main__":
    main()
