import tempfile
import unittest
from pathlib import Path

from database.base import Base
import models  # noqa: F401
from storage.artifact_storage import ArtifactKeyBuilder, ArtifactStorageService
from Tools.InpTools.InpInspector import inspect_section, summarize_sections
from Tools.InpTools.InpValidator import InvalidInpFile, validate_inp_file


class _Stat:
    etag = "test-etag"
    size = 4


class FakeMinio:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.uploads: list[tuple[str, str, str]] = []

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def fput_object(
        self,
        bucket: str,
        object_key: str,
        file_path: str,
        content_type: str | None = None,
    ) -> None:
        self.uploads.append((bucket, object_key, file_path))

    def stat_object(self, bucket: str, object_key: str) -> _Stat:
        return _Stat()


class FoundationTests(unittest.TestCase):
    def test_domain_metadata_contains_core_tables(self) -> None:
        expected = {
            "swmm_models",
            "model_versions",
            "model_parameter_changes",
            "simulation_runs",
            "run_artifacts",
        }
        self.assertTrue(expected.issubset(Base.metadata.tables))

    def test_artifact_key_layout(self) -> None:
        self.assertEqual(
            ArtifactKeyBuilder.model_version("model-1", "version-2"),
            "models/model-1/versions/version-2/model.inp",
        )
        self.assertEqual(
            ArtifactKeyBuilder.run_artifact("run-3", "visual", "out_nodes.json"),
            "runs/run-3/visual/out_nodes.json",
        )

    def test_model_version_upload_uses_private_artifact_bucket(self) -> None:
        fake = FakeMinio()
        storage = ArtifactStorageService(client=fake)
        with tempfile.TemporaryDirectory() as directory:
            inp_path = Path(directory) / "model.inp"
            inp_path.write_text("test", encoding="utf-8")
            stored = storage.upload_model_version(inp_path, "model-1", "version-1")

        self.assertIn(storage.bucket, fake.buckets)
        self.assertEqual(stored.object_key, "models/model-1/versions/version-1/model.inp")
        self.assertEqual(stored.checksum, "test-etag")
        self.assertEqual(len(fake.uploads), 1)

    def test_inp_validation_and_section_inspection(self) -> None:
        content = """[TITLE]
Example model

[OPTIONS]
FLOW_UNITS CFS

[JUNCTIONS]
;;Name Elevation MaxDepth InitDepth SurchargeDepth PondedArea
J1 10.0 3.0 0 0 0
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.inp"
            path.write_text(content, encoding="utf-8")
            validation = validate_inp_file(path)

        summaries = summarize_sections(validation.sections)
        junction_summary = next(item for item in summaries if item["name"] == "JUNCTIONS")
        self.assertEqual(junction_summary["record_count"], 1)
        self.assertTrue(junction_summary["editable"])

        junctions = inspect_section("JUNCTIONS", validation.sections["JUNCTIONS"])
        self.assertEqual(junctions["records"][0]["target"], "J1")
        self.assertEqual(junctions["records"][0]["values"]["elevation"], "10.0")

    def test_inp_without_options_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.inp"
            path.write_text("[TITLE]\nInvalid", encoding="utf-8")
            with self.assertRaises(InvalidInpFile):
                validate_inp_file(path)


if __name__ == "__main__":
    unittest.main()
