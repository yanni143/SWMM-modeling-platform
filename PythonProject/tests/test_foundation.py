import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import models  # noqa: F401
from Controller.controller import app
from database.base import Base
from Service.LisfloodExportService import LisfloodExportService
from Service.ModelService import ModelService
from storage.artifact_storage import ArtifactKeyBuilder, ArtifactStorageService
from swmm_core.lisflood_rate import build_without_sub
from swmm_core.rpt_coupling import build_without_sub_source_data, read_runoff_final_storage
from swmm_core.result_geojson import latest_time_step_layers
from Tools.InpTools.InpGeoJson import build_geojson_layers
from Tools.InpTools.InpInspector import inspect_section, summarize_sections
from Tools.InpTools.InpParameterEditor import (
    ParameterValidationError,
    apply_parameter_changes,
    apply_simulation_options,
    build_parameter_catalog,
    build_simulation_options,
)
from Tools.InpTools.InpRainfallEditor import (
    apply_rainfall_options,
    build_chicago_series,
    build_rainfall_options,
)
from Tools.InpTools.InpValidator import InvalidInpFile, validate_inp_file
from study_areas import STUDY_AREA_SEEDS


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
    @staticmethod
    def simulation_settings():
        return SimpleNamespace(
            simulation_duration_min_seconds=60,
            simulation_duration_max_seconds=86400,
            report_step_min_seconds=10,
            simulation_require_report_step_divisible=False,
            simulation_max_output_steps=1000,
        )

    def test_version_result_routes_are_exposed(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/api/study-areas/latest-model-versions", paths)
        self.assertIn("/api/model-results", paths)
        self.assertIn("/api/model-versions/{version_id}/latest-result/layers", paths)
        self.assertIn("/api/model-versions/{version_id}/latest-result/timeseries", paths)
        self.assertIn("/api/model-versions/{version_id}/latest-result/timeline", paths)
        self.assertIn(
            "/api/model-versions/{version_id}/latest-result/steps/{time_index}", paths
        )
        self.assertIn("/api/runs/{run_id}/lisflood-input", paths)
        self.assertIn(
            "/api/model-versions/{version_id}/latest-result/lisflood-input", paths
        )
        self.assertIn("/api/runs/{run_id}/lisflood-virtual-rainfall", paths)
        self.assertIn(
            "/api/model-versions/{version_id}/latest-result/lisflood-virtual-rainfall",
            paths,
        )
        self.assertNotIn(
            "/api/model-versions/{version_id}/latest-result/depth-timeline", paths
        )
        self.assertNotIn(
            "/api/model-versions/{version_id}/latest-result/depth-steps/{time_index}", paths
        )

    def test_latest_study_area_versions_use_seed_order_and_highest_version(self) -> None:
        lc_seed, jj_seed = STUDY_AREA_SEEDS
        lc_model = SimpleNamespace(id=lc_seed.model_id)
        jj_model = SimpleNamespace(id=jj_seed.model_id)
        lc_version = SimpleNamespace(id=lc_seed.version_id, version=3)
        jj_version = SimpleNamespace(id=jj_seed.version_id, version=2)
        session = SimpleNamespace(
            execute=lambda _: SimpleNamespace(
                all=lambda: [(jj_model, jj_version), (lc_model, lc_version)]
            )
        )
        service = object.__new__(ModelService)

        result = service.list_latest_study_area_versions(session)

        self.assertEqual(
            result,
            [
                {
                    "study_area": "LC",
                    "model_id": lc_seed.model_id,
                    "version_id": lc_seed.version_id,
                    "version": 3,
                },
                {
                    "study_area": "JJ",
                    "model_id": jj_seed.model_id,
                    "version_id": jj_seed.version_id,
                    "version": 2,
                },
            ],
        )

    def test_study_area_inputs_are_valid_and_upload_route_is_absent(self) -> None:
        self.assertEqual({seed.name for seed in STUDY_AREA_SEEDS}, {"LC", "JJ"})
        for seed in STUDY_AREA_SEEDS:
            validation = validate_inp_file(seed.inp_path)
            self.assertIn("OPTIONS", validation.sections)
        routes_source = (
            Path(__file__).parents[1] / "Controller" / "model_routes.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('@router.post("/models"', routes_source)

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
            "COORDINATES": [
                "J1 120.1 31.1",
                "J2 120.2 31.2",
                "S1 120.15 31.15",
            ],
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
        self.assertEqual(
            {feature["properties"]["name"] for feature in layers[2]["geojson"]["features"]},
            {"J1", "J2"},
        )

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

    def test_map_result_layers_only_keep_latest_time_step(self) -> None:
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [120.1, 31.1]},
                "properties": {"name": name, "time_index": time},
            }
            for name in ("J1", "J2")
            for time in (0, 1, 2)
        ]
        layers = [
            {
                "id": "result-nodes",
                "geojson": {"type": "FeatureCollection", "features": features},
            }
        ]

        latest = latest_time_step_layers(layers)

        self.assertEqual(len(latest[0]["geojson"]["features"]), 2)
        self.assertEqual(
            {
                feature["properties"]["time_index"]
                for feature in latest[0]["geojson"]["features"]
            },
            {2},
        )
        self.assertEqual(len(layers[0]["geojson"]["features"]), 6)

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

        subcatchment_fields = {
            field["key"] for field in subcatchment["objects"][0]["fields"]
        }
        self.assertTrue(
            {
                "SUBCATCHMENTS.area",
                "SUBCATCHMENTS.width",
                "INFILTRATION.param1",
                "INFILTRATION.param2",
                "INFILTRATION.param3",
                "INFILTRATION.param4",
            }.isdisjoint(subcatchment_fields)
        )
        self.assertIn("SUBCATCHMENTS.imperv", subcatchment_fields)
        self.assertIn("INFILTRATION.param5", subcatchment_fields)
        conduit_fields = {field["key"] for field in conduit["objects"][0]["fields"]}
        self.assertNotIn("CONDUITS.length", conduit_fields)
        self.assertIn("CONDUITS.roughness", conduit_fields)
        self.assertIn(
            "XSECTIONS.geom1",
            conduit_fields,
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

    def test_simulation_options_are_read_and_updated_in_seconds(self) -> None:
        content = """[OPTIONS]
START_DATE 01/01/2025
START_TIME 00:00:00
REPORT_START_DATE 01/01/2025
REPORT_START_TIME 00:00:00
END_DATE 01/01/2025
END_TIME 02:00:00
REPORT_STEP 00:10:00
ROUTING_STEP 0:00:10

[JUNCTIONS]
J1 0 2
"""
        sections = {
            "OPTIONS": content.split("[OPTIONS]\n", 1)[1].split("\n[JUNCTIONS]", 1)[0].splitlines()
        }
        current = build_simulation_options(sections, self.simulation_settings())
        self.assertEqual(current["duration_seconds"], 7200)
        self.assertEqual(current["report_step_seconds"], 600)

        adjusted, applied = apply_simulation_options(
            content,
            sections,
            {"duration_seconds": 86400, "report_step_seconds": 300},
            self.simulation_settings(),
        )
        self.assertIn("END_DATE             01/02/2025", adjusted)
        self.assertIn("END_TIME             00:00:00", adjusted)
        self.assertIn("REPORT_STEP          00:05:00", adjusted)
        self.assertEqual({item["target"] for item in applied}, {"END_DATE", "END_TIME", "REPORT_STEP"})

    def test_simulation_options_allow_remainder_and_reject_too_small_step(self) -> None:
        sections = {
            "OPTIONS": [
                "START_DATE 01/01/2025",
                "START_TIME 00:00:00",
                "REPORT_START_DATE 01/01/2025",
                "REPORT_START_TIME 00:00:00",
                "END_DATE 01/01/2025",
                "END_TIME 02:00:00",
                "REPORT_STEP 00:10:00",
                "ROUTING_STEP 0:00:10",
            ]
        }
        content = "[OPTIONS]\n" + "\n".join(sections["OPTIONS"])
        adjusted, _ = apply_simulation_options(
            content,
            sections,
            {"duration_seconds": 3700, "report_step_seconds": 600},
            self.simulation_settings(),
        )
        self.assertIn("END_TIME             01:01:40", adjusted)
        self.assertIn("REPORT_STEP          00:10:00", adjusted)
        with self.assertRaisesRegex(ParameterValidationError, "不能小于 10"):
            apply_simulation_options(
                content,
                sections,
                {"duration_seconds": 7200, "report_step_seconds": 5},
                self.simulation_settings(),
            )

    def test_design_rainfall_replaces_only_referenced_time_series(self) -> None:
        content = """[OPTIONS]
FLOW_UNITS CFS
START_DATE 01/01/2025
START_TIME 00:00:00

[RAINGAGES]
RG1 INTENSITY 0.01 1.0 TIMESERIES Rainfall01

[TIMESERIES]
TIDE1 01/01/2025 00:00:00 0.5
Rainfall01 01/01/2025 00:00:00 0.1
Rainfall01 01/01/2025 00:01:00 0.2

[JUNCTIONS]
J1 0 2
"""
        from Tools.InpTools.InpParser import INPParser

        sections = INPParser.parse(content)
        adjusted, changes = apply_rainfall_options(
            content,
            sections,
            {"start_seconds": 600, "duration_seconds": 3000, "total_rainfall_mm": 120.0},
            7200,
        )
        self.assertIn("RG1 INTENSITY 0:05 1.0 TIMESERIES Rainfall01", adjusted)
        self.assertIn("TIDE1 01/01/2025 00:00:00 0.5", adjusted)
        self.assertIn(
            ";@DESIGN_RAIN schema=2 formula=runswmm_chicago start_s=600 "
            "duration_s=3000 total_mm=120",
            adjusted,
        )
        self.assertIn("Rainfall01           01/01/2025 00:10:00", adjusted)
        self.assertNotIn("Rainfall01 01/01/2025 00:01:00 0.2", adjusted)
        self.assertEqual(
            {item["field"] for item in changes},
            {"start_seconds", "duration_seconds", "total_rainfall_mm"},
        )

        parsed = INPParser.parse(adjusted)
        options = build_rainfall_options(parsed, 7200)
        self.assertEqual(options["start_seconds"], 600)
        self.assertEqual(options["duration_seconds"], 3000)
        self.assertEqual(options["end_seconds"], 3600)
        self.assertAlmostEqual(options["total_rainfall_mm"], 120.0)
        self.assertEqual(options["formula"], "runswmm_chicago")

    def test_chicago_series_has_dry_periods_and_expected_peak(self) -> None:
        series = build_chicago_series(600, 3600, 120.0, 7200)
        self.assertEqual(dict(series)[0], 0.0)
        self.assertEqual(dict(series)[4200], 0.0)
        wet = [value for offset, value in series if 600 <= offset < 4200]
        depth = sum(value for value in wet) * 300.0 / 3600.0
        self.assertAlmostEqual(depth, 120.0, places=8)
        peak_offset = max(
            (offset for offset, value in series if 600 <= offset < 4200),
            key=lambda offset: dict(series)[offset],
        )
        self.assertLessEqual(abs(peak_offset - (600 + int(0.4 * 3600))), 300)
        self.assertGreater(max(wet), 0.0)

    def test_design_rainfall_ignores_metadata_without_schema_2(self) -> None:
        content = """[OPTIONS]
FLOW_UNITS CMS
START_DATE 01/01/2025
START_TIME 00:00:00
[RAINGAGES]
RG1 INTENSITY 0:01 1 TIMESERIES Rainfall01
[TIMESERIES]
;@DESIGN_RAIN return_period=5year start_s=600 end_s=3600 dt_s=60
Rainfall01 01/01/2025 00:10:00 12
Rainfall01 01/01/2025 00:11:00 18
"""
        from Tools.InpTools.InpParser import INPParser

        options = build_rainfall_options(INPParser.parse(content), 7200)

        self.assertEqual(options["start_seconds"], 600)
        self.assertEqual(options["duration_seconds"], 360)
        self.assertAlmostEqual(options["total_rainfall_mm"], 2.5)
        self.assertEqual(options["formula"], "existing_timeseries")

    def test_design_rainfall_rejects_invalid_schema_2_metadata(self) -> None:
        content = """[OPTIONS]
FLOW_UNITS CMS
START_DATE 01/01/2025
START_TIME 00:00:00
[RAINGAGES]
RG1 INTENSITY 0:01 1 TIMESERIES Rainfall01
[TIMESERIES]
;@DESIGN_RAIN schema=2 start_s=600 duration_s=120
Rainfall01 01/01/2025 00:10:00 12
"""
        from Tools.InpTools.InpParser import INPParser

        with self.assertRaisesRegex(ParameterValidationError, "元数据格式无效"):
            build_rainfall_options(INPParser.parse(content), 7200)

    def test_design_rainfall_rejects_duration_after_simulation(self) -> None:
        content = """[OPTIONS]
FLOW_UNITS CMS
START_DATE 01/01/2025
START_TIME 00:00:00
[RAINGAGES]
RG1 INTENSITY 0:01 1 TIMESERIES Rainfall01
[TIMESERIES]
Rainfall01 01/01/2025 00:00:00 0
"""
        from Tools.InpTools.InpParser import INPParser

        with self.assertRaisesRegex(ParameterValidationError, "不能超过模拟时长"):
            apply_rainfall_options(
                content,
                INPParser.parse(content),
                {"start_seconds": 0, "duration_seconds": 7260, "total_rainfall_mm": 120.0},
                7200,
            )

    def test_lisflood_without_sub_matches_lc_reference_fixture(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "coupling" / "lc"
        source = build_without_sub_source_data(
            fixture / "LC_MANUAL_23.inp", fixture / "LC_MANUAL_23.rpt"
        )
        actual, _ = build_without_sub(source)
        expected = __import__("json").loads(
            (fixture / "rate_LC_MANUAL_23_without_sub.json").read_text(encoding="utf-8")
        )["rate"]
        actual_by_node = {row["node"]: row for row in actual}
        expected_by_node = {row["node"]: row for row in expected}
        self.assertEqual(set(actual_by_node), set(expected_by_node))
        for node, row in expected_by_node.items():
            self.assertEqual(actual_by_node[node]["coordinate"], row["coordinate"])
            self.assertEqual(actual_by_node[node]["rate"], row["rate"])

    def test_lisflood_virtual_rainfall_uses_report_final_storage(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "coupling" / "lc"
        _, expected_mm = read_runoff_final_storage(fixture / "LC_MANUAL_23.rpt")
        self.assertIsNotNone(expected_mm)
        with tempfile.TemporaryDirectory() as directory:
            output = LisfloodExportService().write_virtual_rainfall(
                fixture / "LC_MANUAL_23.inp",
                fixture / "LC_MANUAL_23.rpt",
                directory,
                "LC_MANUAL_23",
            )
            self.assertIsNotNone(output)
            content = output.read_text(encoding="utf-8")

        values = [
            float(line.split()[-1])
            for line in content.splitlines()
            if line.startswith("TS")
        ]
        self.assertEqual(len(values), 13)
        self.assertEqual(values[-1], 0.0)
        self.assertAlmostEqual(sum(values[:-1]) * 5 / 60, expected_mm, places=3)
