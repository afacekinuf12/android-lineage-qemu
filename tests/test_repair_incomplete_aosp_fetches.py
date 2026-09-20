import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "repair_fetches", Path(__file__).resolve().parents[1] /
    "scripts/repair-incomplete-aosp-fetches.py")
REPAIR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPAIR)
RUN = subprocess.run


class IncompleteFetchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.gitdir = self.source / ".repo/projects/external/webview.git"
        (self.source / ".repo/manifests.git").mkdir(parents=True)
        self.gitdir.parent.mkdir(parents=True)
        self.origin = self.root / "origin"
        self.git("init", "-q", str(self.origin))
        for number in range(3):
            self.git("-C", str(self.origin), "-c", "user.name=Fixture",
                     "-c", "user.email=fixture@example.invalid", "commit",
                     "--allow-empty", "-qm", "commit " + str(number))
        self.git("-C", str(self.origin), "tag", REPAIR.REVISION)
        self.git("init", "--bare", "-q", str(self.gitdir))
        self.git("--git-dir=" + str(self.gitdir), "remote", "add", "aosp",
                 "https://android.googlesource.com/platform/external/chromium-webview")
        self.fetches = []

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return RUN(["git", *args], check=True, capture_output=True, text=True).stdout.strip()

    def local_fetch(self, args, **kwargs):
        if "fetch" in args:
            self.fetches.append(args)
            args = [self.origin.as_uri() if item == "aosp" else item for item in args]
        return RUN(args, **kwargs)

    def repair(self):
        with patch.object(REPAIR.subprocess, "run", side_effect=self.local_fetch):
            return REPAIR.repair(self.source)

    def test_interrupted_empty_repo_resumes_with_one_commit(self):
        self.assertEqual(["external/webview.git"], self.repair())
        self.assertTrue((self.gitdir / "shallow").is_file())
        self.assertEqual("1", self.git("--git-dir=" + str(self.gitdir),
                                      "rev-list", "--count", REPAIR.REVISION))
        self.assertEqual([], self.repair())
        self.assertEqual(1, len(self.fetches))

    def test_established_full_history_is_not_reshallowed(self):
        self.git("--git-dir=" + str(self.gitdir), "fetch", self.origin.as_uri(),
                 "tag", REPAIR.REVISION)
        self.assertFalse((self.gitdir / "shallow").exists())
        self.assertEqual([], self.repair())
        self.assertEqual([], self.fetches)
        self.assertEqual("3", self.git("--git-dir=" + str(self.gitdir),
                                      "rev-list", "--count", REPAIR.REVISION))
