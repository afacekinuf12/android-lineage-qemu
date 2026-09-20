#!/usr/bin/env python3
"""Exercise a patched Android uiautomator shell wrapper with a fake app_process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).read_text()
with tempfile.TemporaryDirectory(prefix="uiautomator-wrapper-") as temp:
    root = Path(temp)
    base = root / "system"
    local = root / "local"
    (base / "framework").mkdir(parents=True)
    local.mkdir()
    jars = ["android.test.base.jar", "android.test.mock.jar", "android.test.runner.jar", "uiautomator.jar"]
    for name in jars:
        (base / "framework" / name).touch()
    test_jar = local / "sample.jar"
    test_jar.touch()
    wrapper = root / "uiautomator.sh"
    wrapper.write_text(source.replace("export base=/system", "export base=" + str(base))
                       .replace("export run_base=/data/local/tmp", "export run_base=" + str(local)))
    fake = root / "app_process"
    fake.write_text("#!" + sys.executable + "\nimport os,json,sys\n"
                    "print('CAPTURE='+json.dumps({'classpath':os.environ['CLASSPATH'], 'args':sys.argv[1:]}))\n")
    fake.chmod(0o700)
    env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"], USER_ID="0")
    for args in (["dump", "/data/local/tmp/test.xml"],
                 ["runtest", str(test_jar), "-c", "local.observer.Sample"],
                 ["runtest", "sample.jar", "-c", "local.observer.Sample", "--nohup"]):
        result = subprocess.run(["bash", str(wrapper)] + args, env=env, text=True,
                                capture_output=True, check=True, timeout=5)
        capture = next(line[8:] for line in result.stdout.splitlines() if line.startswith("CAPTURE="))
        parsed = json.loads(capture)
        expected = [str(base / "framework" / jar) for jar in jars]
        observed = [p for p in parsed["classpath"].split(":") if p]
        if args[0] == "runtest":
            expected.append(str(test_jar))
        if observed != expected:
            sys.exit("incorrect runner classpath: " + repr(observed))
        if parsed["args"][:3] != [str(base / "bin"), "com.android.commands.uiautomator.Launcher", args[0]]:
            sys.exit("launcher arguments changed")
        if "--nohup" in parsed["args"]:
            sys.exit("wrapper failed to consume --nohup")
    print("UI Automator wrapper: dump, absolute/relative runtest and --nohup passed")
