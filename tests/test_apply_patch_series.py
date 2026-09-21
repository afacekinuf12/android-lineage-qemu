import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "patch_series", ROOT / "scripts/apply-patch-series.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PatchSeriesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.git("init", "-q")
        self.target = self.project / "config"
        self.base = "header\nfirst=old\nsecond=old\nfooter\n"
        self.middle = self.base.replace("first=old", "first=new")
        self.final = self.middle.replace("second=old", "second=new")
        self.target.write_text(self.base)
        (self.project / "unrelated").write_text("original\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "base")
        self.target.write_text(self.middle)
        first = self.root / "first.patch"
        first.write_bytes(self.git("diff", "--", "config"))
        self.git("add", "config")
        self.target.write_text(self.final)
        second = self.root / "second.patch"
        second.write_bytes(self.git("diff", "--", "config"))
        self.git("reset", "--hard", "-q", "HEAD")
        self.patches = [first, second]

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.project), *args], check=True,
                              capture_output=True).stdout

    def test_overlapping_series_reapplies_and_preserves_real_index(self):
        unrelated = self.project / "unrelated"
        unrelated.write_text("user staged change\n")
        self.git("add", "unrelated")
        staged = self.git("diff", "--cached", "--binary")
        head = self.git("rev-parse", "HEAD")
        MODULE.apply_series(self.project, self.patches)
        self.assertEqual(self.final, self.target.read_text())
        old_check = subprocess.run(
            ["git", "-C", str(self.project), "apply", "--reverse", "--check",
             str(self.patches[0])], capture_output=True)
        self.assertNotEqual(0, old_check.returncode)
        MODULE.apply_series(self.project, self.patches)
        self.assertEqual(self.final, self.target.read_text())
        self.assertEqual(staged, self.git("diff", "--cached", "--binary"))
        self.assertEqual(head, self.git("rev-parse", "HEAD"))
        self.assertEqual("user staged change\n", unrelated.read_text())

    def test_conflicting_local_change_is_preserved(self):
        self.target.write_text(self.base.replace("first=old", "first=user"))
        before = self.git("diff", "--binary")
        with self.assertRaisesRegex(RuntimeError, "left unchanged"):
            MODULE.apply_series(self.project, self.patches)
        self.assertEqual(before, self.git("diff", "--binary"))

    def test_partial_old_series_is_rejected_without_overwriting(self):
        self.target.write_text(self.middle)
        with self.assertRaisesRegex(RuntimeError, "left unchanged"):
            MODULE.apply_series(self.project, self.patches)
        self.assertEqual(self.middle, self.target.read_text())

    def test_invalid_later_patch_does_not_apply_earlier_patch(self):
        self.patches[1].write_text("invalid patch\n")
        with self.assertRaisesRegex(RuntimeError, "does not apply"):
            MODULE.apply_series(self.project, self.patches)
        self.assertEqual(self.base, self.target.read_text())
        self.assertEqual(b"", self.git("status", "--porcelain"))


if __name__ == "__main__":
    unittest.main()
