#!/usr/bin/env python3
"""Apply a project's complete patch series without changing its real index."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def apply_series(project, patches):
    project = Path(project).resolve()
    patches = [Path(patch).resolve() for patch in patches]

    def git(*args, **kwargs):
        return subprocess.run(["git", "-C", str(project), *args],
                              capture_output=True, **kwargs)

    # Later patches can change the context of earlier ones. Build a single
    # HEAD-to-final diff in an isolated index so reapplication checks the final
    # state, not each intermediate state. Neither HEAD nor the real index moves.
    with tempfile.TemporaryDirectory(prefix="aosp-patch-series-") as temp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp) / "index"))
        git("read-tree", "HEAD", env=env, check=True)
        for patch in patches:
            result = git("apply", "--cached", str(patch), env=env)
            if result.returncode:
                raise RuntimeError("Patch does not apply to project HEAD: {}\n{}".format(
                    patch.name, result.stderr.decode(errors="replace")))
        delta = git("diff", "--cached", "--binary", "--no-ext-diff", "HEAD",
                    env=env, check=True).stdout
    if not delta:
        raise RuntimeError("Patch series has no changes")
    if git("apply", "--reverse", "--check", input=delta).returncode == 0:
        print("Patch series already applied: " + str(project))
        return
    result = git("apply", "--check", input=delta)
    if result.returncode:
        raise RuntimeError(
            "Project matches neither the base nor the complete patch series; "
            "working files were left unchanged: {}\n{}".format(
                project, result.stderr.decode(errors="replace")))
    git("apply", input=delta, check=True)
    print("Applied patch series: " + str(project))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("patches", nargs="+", type=Path)
    args = parser.parse_args()
    apply_series(args.project, args.patches)


if __name__ == "__main__":
    main()
