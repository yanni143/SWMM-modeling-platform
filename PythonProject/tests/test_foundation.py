import tempfile
import unittest
from pathlib import Path

from database.base import Base
import models  # noqa: F401
from storage.artifact_storage import ArtifactKeyBuilder, ArtifactStorageService
from Tools.InpTools.InpInspector import inspect_section, summarize_sections
from Tools.InpTools.InpGeoJson import build_geojson_layers
from Tools.InpTools.InpParameterEditor import (
    ParameterValidationError,
    apply_parameter_changes,
    build_parameter_catalog,
)
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

    def test_inp_spatial_sections_build_geojson_layers(self) -> None:
        sections = {
            "JUNCTIONS": ["J1 0 2", "J2 0 2"],
            "CONDUITS": ["C1 J1 J2 100 0.013 0 0"],
            "SUBCATCHMENTS": ["S1 RG1 J1 1 30 50 1 0"],
            "COORDINATES": ["J1 120.1 31.1", "J2 120.2 31.2"],
            "VERTICES": ["C1 120.15 31.16"],
            "POLYGONS": ["S1 120.1 31.1", "S1 120.2 31.1", "S1 120.2 31.2"],
        }

        layers = build_geojson_layers(sections)

        self.assertEqual(
            [layer["id"] for layer in layers],
            ["inp-subcatchments", "inp-conduits", "inp-nodes"],
        )
        self.assertEqual(
            layers[1]["geojson"]["features"][0]["geometry"]["type"], "LineString"
        )
        self.assertEqual(len(layers[2]["geojson"]["features"]), 2)

    def test_projected_inp_coordinates_are_converted_for_mapbox(self) -> None:
        sections = {
            "JUNCTIONS": ["J1 0 2"],
            "COORDINATES": ["J1 581043.41 3435679.38"],
        }

        layers = build_geojson_layers(sections, source_crs="EPSG:4549")
        point = layers[0]["geojson"]["features"][0]["geometry"]["coordinates"]

        self.assertAlmostEqual(point[0], 120.848921, places=5)
        self.assertAlmostEqual(point[1], 31.039645, places=5)
        self.assertEqual(layers[0]["display_crs"], "EPSG:4326")

    def test_parameter_catalog_joins_safe_fields_by_object(self) -> None:
        sections = {
            "OPTIONS": ["INFILTRATION HORTON"],
            "SUBCATCHMENTS": ["S1 G1 J1 1.0 40 100 1.0 0"],
            "SUBAREAS": ["S1 0.01 0.10 1.27 2.54 25 OUTLET"],
            "INFILTRATION": ["S1 75 10 4 7 0"],
            "CONDUITS": ["C1 J1 J2 100 0.013 0 0 0 0"],
            "XSECTIONS": ["C1 CIRCULAR 1.2 0 0 0 1"],
        }

        groups = build_parameter_catalog(sections)
        subcatchment = next(group for group in groups if group["id"] == "subcatchments")
        conduit = next(group for group in groups if group["id"] == "conduits")

        self.assertGreater(len(subcatchment["objects"][0]["fields"]), 8)
        self.assertIn(
            "XSECTIONS.geom1",
            [field["key"] for field in conduit["objects"][0]["fields"]],
        )

    def test_safe_parameter_change_updates_only_whitelisted_value(self) -> None:
        content = "[CONDUITS]\nC1 J1 J2 100 0.013 0 0 0 0\n"
        adjusted, applied = apply_parameter_changes(
            content,
            [{"section": "CONDUITS", "target": "C1", "field": "roughness", "new_value": "0.02"}],
        )

        self.assertIn("C1 J1 J2 100 0.02", adjusted)
        self.assertEqual(applied[0]["old_value"], "0.013")
        with self.assertRaises(ParameterValidationError):
            apply_parameter_changes(
                content,
                [{"section": "CONDUITS", "target": "C1", "field": "from_node", "new_value": "J9"}],
            )


if __name__ == "__main__":
    unittest.main()
