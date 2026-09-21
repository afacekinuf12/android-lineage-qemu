#!/usr/bin/env python3
"""Exercise the patched board's Ninja environment selection with GNU Make."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    board = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="jvm-guard-") as temp:
        root = Path(temp)
        for relative in (
            "device/mainline/common/BoardConfigMainlineCommon.mk",
            "device/google/cuttlefish/shared/swiftshader/BoardConfig.mk",
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        harness = root / "check.mk"
        harness.write_text(
            "BUILD_BROKEN_NINJA_USES_ENV_VARS := EXISTING_ALLOWED\n"
            "include " + str(board) + "\n"
            "all:\n\t@echo ALLOWED=$(BUILD_BROKEN_NINJA_USES_ENV_VARS)\n")
        for value, allowed in (
            ("", False),
            ("-Xmx4G", False),
            ("-XX:+DisableAttachMechanism", True),
            ("-XX:+DisableAttachMechanism -Xmx4G", False),
        ):
            result = subprocess.run(
                ["make", "-s", "-f", str(harness)], cwd=root,
                env=dict(os.environ, JAVA_TOOL_OPTIONS=value),
                capture_output=True, text=True, timeout=10, check=True)
            expected = "ALLOWED=EXISTING_ALLOWED" + (" JAVA_TOOL_OPTIONS" if allowed else "")
            if result.stdout.strip() != expected:
                raise RuntimeError("Unexpected Ninja environment selection: " + result.stdout)
    print("Ninja JVM guard: exact value accepted; unrelated values rejected; existing vars retained.")


if __name__ == "__main__":
    main()
