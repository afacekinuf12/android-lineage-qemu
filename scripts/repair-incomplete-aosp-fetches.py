#!/usr/bin/env python3
"""Resume empty AOSP repositories as shallow clones after an interrupted sync.

Current repo treats an existing git directory without a shallow file as a
manually unshallowed repository. An interrupted first fetch also has that
shape, so it can unexpectedly download all history on the next sync.
Only repositories with no refs and no shallow boundary are bootstrapped here.
"""
from pathlib import Path
import subprocess
import sys

REVISION = "android-16.0.0_r4"


def repair(root):
    root = Path(root).resolve()
    if not (root / ".repo/manifests.git").is_dir():
        raise ValueError("Expected the dedicated AOSP repo checkout")
    repaired = []
    for config in sorted((root / ".repo/projects").rglob("config")):
        gitdir = config.parent
        if not gitdir.name.endswith(".git") or (gitdir / "shallow").exists():
            continue
        git = ["git", "--git-dir=" + str(gitdir)]
        refs = subprocess.check_output(git + ["for-each-ref", "--format=%(refname)"],
                                       text=True).strip()
        if refs:
            continue
        remote = subprocess.run(git + ["config", "--get", "remote.aosp.url"],
                                capture_output=True, text=True, check=False)
        if remote.returncode or not remote.stdout.strip().startswith(
                "https://android.googlesource.com/"):
            continue
        relative = str(gitdir.relative_to(root / ".repo/projects"))
        print("Resume interrupted shallow fetch: " + relative, flush=True)
        subprocess.run(
            git + ["fetch", "--depth=1", "--no-tags", "--no-recurse-submodules",
                   "aosp", "tag", REVISION],
            check=True,
        )
        repaired.append(relative)
    print("Repaired {} incomplete AOSP fetches".format(len(repaired)), flush=True)
    return repaired


if __name__ == "__main__":
    repair(sys.argv[1])
