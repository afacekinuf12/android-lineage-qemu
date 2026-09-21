import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("aosp_output", ROOT / "scripts/select-aosp-output.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AospOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name).resolve()
        self.manifest = b'<manifest><project name="platform" revision="actual-commit"/></manifest>\n'

    def tearDown(self):
        self.temp.cleanup()

    def select(self, resume=None, release="bp2a", manifest=None):
        return MODULE.select_output(self.source, release, manifest or self.manifest, resume)

    def test_new_builds_are_isolated_and_explicit_resume_preserves_compiled_files(self):
        first = self.select()
        second = self.select()
        self.assertNotEqual(first, second)
        compiled = first / "compiled.o"
        compiled.write_bytes(b"compiled object")
        self.assertEqual(first, self.select(first))
        self.assertEqual(b"compiled object", compiled.read_bytes())

    def test_wrong_release_or_source_revision_rejected_without_changes(self):
        output = self.select()
        marker = (output / MODULE.MARKER).read_bytes()
        for options in ({"release": "other"}, {"manifest": b"<manifest/>"}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, "identity differs"):
                self.select(output, **options)
        self.assertEqual(marker, (output / MODULE.MARKER).read_bytes())

    def test_wrong_product_or_missing_identity_cannot_resume(self):
        output = self.select()
        marker = output / MODULE.MARKER
        data = json.loads(marker.read_text())
        data["product"] = "lineage_virtio_arm64only"
        marker.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "identity differs"):
            self.select(output)
        marker.unlink()
        with self.assertRaisesRegex(ValueError, "existing AOSP output identity"):
            self.select(output)

    def test_other_tree_or_symlink_cannot_resume(self):
        output = self.select()
        link = output.parent / "virtio-aosp.link"
        link.symlink_to(output, target_is_directory=True)
        for candidate in (link, self.source / "old-lineage"):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(ValueError, "directly inside"):
                self.select(candidate)

    def test_manifest_tampering_is_rejected(self):
        output = self.select()
        (output / "resolved-manifest.xml").write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "Recorded source manifest differs"):
            self.select(output)


if __name__ == "__main__":
    unittest.main()
