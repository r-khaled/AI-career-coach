import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ingestion import prepare_lab


class IngestionPackageTests(unittest.TestCase):
    def test_source_and_intermediate_buckets_cannot_be_the_same(self):
        with self.assertRaises(ValueError):
            prepare_lab.prepare(bucket="same", intermediate_bucket="same", account_id="123456789012", region="us-east-2", stack_name="example")

    def test_artifacts_use_selected_outputs_and_zip_contains_only_runtime_code(self):
        original = prepare_lab.ROOT
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            shutil.copyfile(original / "internal_courses.md", target / "internal_courses.md")
            (target / "ingestion").mkdir()
            for name in ["__init__.py", "course_chunker.py", "transform.py"]:
                shutil.copyfile(original / "ingestion" / name, target / "ingestion" / name)
            with patch.object(prepare_lab, "ROOT", target), contextlib.redirect_stdout(io.StringIO()):
                prepare_lab.prepare(bucket="example-bucket", intermediate_bucket="example-intermediate", account_id="123456789012", region="us-west-2", stack_name="example")
                folder = target / ".lab/ingestion-deployment"
                before = (folder / "course-transform.zip").read_bytes()
                prepare_lab.prepare(bucket="example-bucket", intermediate_bucket="example-intermediate", account_id="123456789012", region="us-west-2", stack_name="example")
            self.assertEqual(before, (folder / "course-transform.zip").read_bytes())
            env = json.loads((folder / "lambda-environment.json").read_text())
            self.assertEqual(env["INTERMEDIATE_BUCKET"], "example-intermediate")
            self.assertEqual(env["CATALOG_SOURCE_URI"], "s3://example-bucket/internal_courses.md")
            policy = json.loads((folder / "kb-role-transformation-policy.json").read_text())
            self.assertEqual(policy["Statement"][0]["Resource"], ["arn:aws:lambda:us-west-2:123456789012:function:example-ingestion-transform", "arn:aws:lambda:us-west-2:123456789012:function:example-ingestion-transform:$LATEST"])
            manifest = json.loads((folder / "manifest.json").read_text())
            self.assertEqual(manifest["course_chunks"], 40)
            self.assertEqual(manifest["context_chunks"], 2)
            self.assertEqual(manifest["artifact_s3_key"], "lambda-artifacts/" + manifest["zip_sha256"] + ".zip")
            with zipfile.ZipFile(folder / "course-transform.zip") as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), {"ingestion/__init__.py", "ingestion/course_chunker.py", "ingestion/transform.py"})
                for name in archive.namelist():
                    self.assertEqual(archive.read(name), (original / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
