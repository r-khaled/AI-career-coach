import copy
import io
import json
from pathlib import Path
import unittest

from ingestion.course_chunker import chunk_catalog
from ingestion.transform import transform

CATALOG = Path(__file__).resolve().parents[1] / "internal_courses.md"
SOURCE = "s3://catalog-bucket/internal_courses.md"


class CourseChunkerTests(unittest.TestCase):
    def setUp(self):
        self.text = CATALOG.read_text(encoding="utf-8")
        self.chunks = chunk_catalog(self.text)
        self.courses = [c for c in self.chunks if c["contentMetadata"]["record_type"] == "course"]

    def test_current_catalog_has_complete_distinct_course_records(self):
        self.assertEqual(len(self.courses), 40)
        self.assertEqual(len({c["contentMetadata"]["course_id"] for c in self.courses}), 40)
        for chunk in self.courses:
            self.assertEqual(chunk["contentBody"].count("### Course ID:"), 1)
            self.assertEqual(chunk["contentBody"].count("**"), 18)
            # Every original field is retained verbatim in the chunk body.
            self.assertIn(chunk["contentBody"], self.text)
            self.assertIsInstance(chunk["contentMetadata"]["duration_hours"], int)

    def test_global_notes_are_retained_separately(self):
        contexts = [c for c in self.chunks if c["contentMetadata"]["record_type"] == "catalog_context"]
        self.assertEqual(len(contexts), 2)
        self.assertIn("How to read this catalog", contexts[0]["contentBody"])
        self.assertIn("Example learning paths", contexts[1]["contentBody"])
        self.assertIn("Coverage boundaries", contexts[1]["contentBody"])
        self.assertNotIn("course_id", contexts[0]["contentMetadata"])

    def test_known_course_metadata_and_prerequisites(self):
        courses = {c["contentMetadata"]["course_id"]: c["contentMetadata"] for c in self.courses}
        self.assertEqual(courses["FWE-301"]["duration_hours"], 24)
        self.assertEqual(courses["FWE-301"]["level"], "Advanced")
        self.assertEqual(courses["SEC-201"]["prerequisites"], ["SEC-101", "BKE-101"])
        self.assertEqual(courses["QAE-210"]["duration_hours"], 22)
        self.assertFalse(courses["CLD-001"]["has_prerequisites"])
        self.assertNotIn("prerequisites", courses["CLD-001"])

    def test_invalid_catalogs_fail_instead_of_losing_or_mixing_data(self):
        invalid = [
            self.text.replace("### Course ID: CLD-101", "### Course ID: CLD-001", 1),
            self.text.replace("**Track:** Cloud Architecture\n", "", 1),
            self.text.replace("12 hours, including practice.", "twelve hours", 1),
            self.text.replace("**Level:** Foundation", "**Level:** Expert", 1),
            self.text.replace("**Prerequisites:** CLD-001", "**Prerequisites:** CLD-999", 1),
            self.text.replace("**Description:**", "**Description:** " + "x" * 6000, 1),
            self.text.replace("## DevOps and Site Reliability Track", "Unclassified business rule", 1),
        ]
        for text in invalid:
            with self.subTest(text=text[:20]), self.assertRaises(ValueError):
                chunk_catalog(text)


class MemoryS3:
    def __init__(self, source):
        self.objects = {"kb-intermediate/input.json": json.dumps({"fileContents": [
            {"contentBody": source, "contentType": "TEXT", "contentMetadata": {}}
        ]}).encode()}
        self.writes = []

    def get_object(self, *, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body
        self.writes.append(Key)


class TransformationContractTests(unittest.TestCase):
    def setUp(self):
        self.s3 = MemoryS3(CATALOG.read_text())
        self.event = {
            "version": "1.0", "bucketName": "intermediate-bucket", "priorTask": "CHUNKING",
            "ingestionJobId": "job-1", "knowledgeBaseId": "kb-1", "dataSourceId": "ds-1",
            "inputFiles": [{
                "originalFileLocation": {"type": "S3", "s3_location": {"uri": SOURCE}},
                "fileMetadata": {"department": "learning"},
                "contentBatches": [{"key": "kb-intermediate/input.json"}],
            }],
        }

    def run_transform(self, event=None):
        return transform(event or self.event, self.s3, bucket="intermediate-bucket",
                         prefix="kb-intermediate/", source_uri=SOURCE)

    def test_bedrock_contract_preserves_file_metadata_and_returns_s3_references(self):
        response = self.run_transform()
        output = response["outputFiles"][0]
        self.assertEqual(output["originalFileLocation"], self.event["inputFiles"][0]["originalFileLocation"])
        self.assertEqual(output["fileMetadata"], {"department": "learning"})
        key = output["contentBatches"][0]["key"]
        self.assertTrue(key.startswith("kb-intermediate/custom/"))
        self.assertEqual(len(json.loads(self.s3.objects[key])["fileContents"]), 42)
        self.assertEqual(self.run_transform(), response)  # retries use the same output object

    def test_actual_bedrock_plain_text_content_type_is_preserved(self):
        payload = json.loads(self.s3.objects["kb-intermediate/input.json"])
        payload["fileContents"][0]["contentType"] = "PLAIN_TEXT"
        self.s3.objects["kb-intermediate/input.json"] = json.dumps(payload).encode()
        result = self.run_transform()
        key = result["outputFiles"][0]["contentBatches"][0]["key"]
        actual = json.loads(self.s3.objects[key])["fileContents"]
        self.assertEqual(len(actual), 42)
        self.assertTrue(all(item["contentType"] == "PLAIN_TEXT" for item in actual))
        expected = chunk_catalog(CATALOG.read_text())
        self.assertEqual([(c["contentBody"], c["contentMetadata"]) for c in actual],
                         [(c["contentBody"], c["contentMetadata"]) for c in expected])

    def test_invalid_boundaries_fail_before_writing(self):
        variants = []
        for field, value in [("bucketName", "other"), ("version", "2.0")]:
            event = copy.deepcopy(self.event)
            event[field] = value
            variants.append(event)
        for key in ["outside/input.json", "kb-intermediate/../secret", ""]:
            event = copy.deepcopy(self.event)
            event["inputFiles"][0]["contentBatches"][0]["key"] = key
            variants.append(event)
        event = copy.deepcopy(self.event)
        event["inputFiles"][0]["originalFileLocation"]["s3_location"]["uri"] = "s3://other/private.txt"
        variants.append(event)
        for event in variants:
            with self.subTest(event=event), self.assertRaises(ValueError):
                self.run_transform(event)
        self.assertEqual(self.s3.writes, [])

    def test_nontext_or_unexpected_metadata_fails_visibly(self):
        for changes in [{"contentType": "PDF"}, {"contentMetadata": {"level": "wrong"}}]:
            payload = json.loads(self.s3.objects["kb-intermediate/input.json"])
            payload["fileContents"][0].update(changes)
            self.s3.objects["kb-intermediate/input.json"] = json.dumps(payload).encode()
            with self.assertRaises(ValueError):
                self.run_transform()
        self.assertEqual(self.s3.writes, [])


if __name__ == "__main__":
    unittest.main()
