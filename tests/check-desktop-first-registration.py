#!/usr/bin/env python3
"""Compile the real repository with boundary fakes; exercise listener availability."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("--kotlinc", required=True)
parser.add_argument("--java", required=True)
args = parser.parse_args()
sources = {
    "Flags.kt": """package android.window
object DesktopExperienceFlags {
    object ENABLE_DESKTOP_FIRST_LISTENER { var isTrue: Boolean = false }
}
""",
    "Singleton.kt": "package com.android.systemui.dagger\nannotation class SysUISingleton\n",
    "Inject.kt": "package javax.inject\nannotation class Inject\n",
    "Listener.kt": """package com.android.wm.shell.shared.desktopmode
interface DesktopFirstListener { fun onStateChanged(displayId: Int, isDesktopFirstEnabled: Boolean) }
interface DesktopState { val canEnterDesktopMode: Boolean }
""",
    "Mode.kt": """package com.android.wm.shell.desktopmode
import com.android.wm.shell.shared.desktopmode.DesktopFirstListener
interface DesktopMode { fun registerDesktopFirstListener(listener: DesktopFirstListener) }
""",
    "Main.kt": """import android.window.DesktopExperienceFlags
import com.android.systemui.desktop.DesktopFirstRepository
import com.android.wm.shell.desktopmode.DesktopMode
import com.android.wm.shell.shared.desktopmode.DesktopFirstListener
import com.android.wm.shell.shared.desktopmode.DesktopState
import java.util.Optional
fun main() {
    var count = 0
    for (canEnter in listOf(false, true)) {
        for (enabled in listOf(false, true)) {
            for (present in listOf(false, true)) {
                DesktopExperienceFlags.ENABLE_DESKTOP_FIRST_LISTENER.isTrue = enabled
                var registrations = 0
                var registered: DesktopFirstListener? = null
                val mode = object : DesktopMode {
                    override fun registerDesktopFirstListener(listener: DesktopFirstListener) {
                        check(canEnter && enabled) { "Unavailable listener manager was used" }
                        registrations++
                        registered = listener
                    }
                }
                val state = object : DesktopState {
                    override val canEnterDesktopMode = canEnter
                }
                val repository = DesktopFirstRepository(
                    if (present) Optional.of(mode) else Optional.empty(), state)
                check(registrations == if (canEnter && enabled && present) 1 else 0)
                check(!repository.isDisplayDesktopFirst(7))
                registered?.onStateChanged(7, true)
                check(repository.isDisplayDesktopFirst(7) == (registrations == 1))
                check(!repository.isDisplayDesktopFirst(8))
                registered?.onStateChanged(7, false)
                check(!repository.isDisplayDesktopFirst(7))
                count++
            }
        }
    }
    println("Desktop-first repository: $count availability combinations passed")
}
""",
}
with tempfile.TemporaryDirectory(prefix="desktop-first-") as temp:
    root = Path(temp)
    shutil.copyfile(args.source, root / "DesktopFirstRepository.kt")
    for name, text in sources.items():
        (root / name).write_text(text)
    env = dict(os.environ, JAVA_HOME=str(Path(args.java).resolve().parent.parent),
               JAVA_TOOL_OPTIONS="-XX:+DisableAttachMechanism")
    subprocess.run([args.kotlinc, *map(str, sorted(root.glob("*.kt"))),
                    "-include-runtime", "-d", str(root / "check.jar")],
                   env=env, check=True, timeout=60)
    subprocess.run([args.java, "-jar", str(root / "check.jar")],
                   env=env, check=True, timeout=15)
