from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from config import Settings
from models.domain import ModelVersion, SwmmModel
from schemas.parameter import RainfallOptions, RainfallOptionsInput
from Service.ModelService import ModelService
from study_areas import JJ_REAL_INPUT_PATH, STUDY_AREA_SEEDS, rainfall_inputs
from Tools.InpTools.InpParameterEditor import (
    ParameterValidationError,
    apply_parameter_changes,
    build_simulation_options,
)
from Tools.InpTools.InpParser import INPParser
from Tools.InpTools.RainfallScenario import (
    EVENT_ID,
    apply_rainfall_scenario,
    prepare_rainfall,
    rainfall_catalog,
    real_event,
)
from Tools.InpTools.RainfallSeries import read_series


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(
        simulation_duration_min_seconds=60,
        simulation_duration_max_seconds=172800,
        report_step_min_seconds=10,
        simulation_require_report_step_divisible=False,
        simulation_max_output_steps=1000,
        resolved_runtime_dir=tmp_path,
    )


@pytest.fixture
def design():
    return STUDY_AREA_SEEDS[1].inp_path.read_text(encoding="utf-8")


@pytest.fixture
def observed():
    return JJ_REAL_INPUT_PATH.read_text(encoding="utf-8")


def test_event_is_interval_depth_data_identical_to_original(observed, settings):
    event = real_event()
    original = read_series(INPParser.parse(observed), 172800)
    assert event["values_mm"] == pytest.approx(original["values_mm"], abs=1e-10)
    assert len(event["values_mm"]) == 576
    assert event["total_rainfall_mm"] == 226.2
    assert event["peak_rainfall_mm_h"] == pytest.approx(132)
    assert event["start_datetime"] == "2026-09-13T00:00:00"


def test_one_baseline_per_area_and_no_second_root_seed(settings):
    for seed in STUDY_AREA_SEEDS:
        inputs = rainfall_inputs(seed.model_id)
        assert len(inputs) == 1
        assert inputs[0]["baseline_version_id"] == seed.version_id
    service = object.__new__(ModelService)
    calls = []
    service._ensure_seed = lambda session, seed: calls.append(seed.version_id)
    service.ensure_study_areas(None)
    assert calls == [seed.version_id for seed in STUDY_AREA_SEEDS]


def test_legacy_real_input_remains_readable_and_engineering_edits_preserve_series(
    observed, settings
):
    before = INPParser.parse(observed)
    catalog = RainfallOptions.model_validate(rainfall_catalog(before, "JJ", settings, "real"))
    assert catalog.mode == "real"
    assert catalog.total_rainfall_mm == 226.2
    target = next(line.split()[0] for line in before["CONDUITS"] if not line.startswith(";"))
    adjusted, _ = apply_parameter_changes(
        observed,
        [{"section": "CONDUITS", "target": target, "field": "roughness", "new_value": "0.02"}],
    )
    saved, changes = apply_rainfall_scenario(
        adjusted,
        "JJ",
        settings,
        {"duration_seconds": 172800, "report_step_seconds": 600},
        rainfall_mode="real",
    )
    after = INPParser.parse(saved)
    assert after["TIMESERIES"] == before["TIMESERIES"]
    assert after["RAINGAGES"] == before["RAINGAGES"]
    assert [change["target"] for change in changes] == ["REPORT_STEP"]


def test_design_to_real_retains_engineering_and_model_dates(design, settings):
    content, _ = apply_rainfall_scenario(
        design,
        "JJ",
        settings,
        {"duration_seconds": 172800, "report_step_seconds": 300},
        {"mode": "real", "event_id": EVENT_ID},
    )
    before, after = INPParser.parse(design), INPParser.parse(content)
    for section in set(before) - {"OPTIONS", "RAINGAGES", "TIMESERIES"}:
        assert before[section] == after[section]
    simulation = build_simulation_options(after, settings)
    assert simulation["start_datetime"] == "2025-07-15T00:00:00"
    rain = rainfall_catalog(after, "JJ", settings)
    assert rain["mode"] == "real" and rain["total_rainfall_mm"] == 226.2
    assert rain["values_mm"] == real_event()["values_mm"]
    # Re-submitting the exact same rain does not generate a spurious version.
    unchanged, changes = apply_rainfall_scenario(
        content, "JJ", settings, rainfall_options={"mode": "real", "event_id": EVENT_ID}
    )
    assert unchanged == content and changes == []


def test_real_can_be_replaced_with_design_or_custom(observed, settings):
    for request in [
        {"mode": "design", "start_seconds": 300, "duration_seconds": 600, "total_rainfall_mm": 5},
        {"mode": "custom", "start_seconds": 17, "time_step_seconds": 61, "values_mm": [0, 1, 2, 0]},
    ]:
        content, changes = apply_rainfall_scenario(
            observed, "JJ", settings, rainfall_options=request, rainfall_mode="real"
        )
        rain = rainfall_catalog(INPParser.parse(content), "JJ", settings, "real")
        assert rain["mode"] == request["mode"]
        assert changes
        assert rain["event_id"] is None
        if request["mode"] == "custom":
            assert rain["values_mm"] == [0, 1, 2, 0]
            assert rain["duration_seconds"] == 244


def test_same_total_and_duration_different_shape_is_a_change(design, settings):
    request = {
        "mode": "custom",
        "start_seconds": 0,
        "time_step_seconds": 300,
        "values_mm": [1, 2, 0],
    }
    first, _ = apply_rainfall_scenario(design, "JJ", settings, rainfall_options=request)
    second, changes = apply_rainfall_scenario(
        first, "JJ", settings, rainfall_options={**request, "values_mm": [2, 1, 0]}
    )
    a, b = [
        rainfall_catalog(INPParser.parse(content), "JJ", settings) for content in [first, second]
    ]
    assert a["total_rainfall_mm"] == b["total_rainfall_mm"] == 3
    assert a["duration_seconds"] == b["duration_seconds"]
    assert a["series_checksum"] != b["series_checksum"]
    assert len(changes) == 1


def test_only_rain_series_is_replaced_and_zero_rain_is_valid(design, settings):
    content = design.replace("[TIMESERIES]", "[TIMESERIES]\nTIDE 07/15/2025 00:00:00 0.5")
    adjusted, _ = apply_rainfall_scenario(
        content,
        "JJ",
        settings,
        rainfall_options={
            "mode": "custom",
            "start_seconds": 0,
            "time_step_seconds": 300,
            "values_mm": [0, 0],
        },
    )
    assert "TIDE 07/15/2025 00:00:00 0.5" in adjusted
    rain = rainfall_catalog(INPParser.parse(adjusted), "JJ", settings)
    assert rain["values_mm"] == [0, 0] and rain["total_rainfall_mm"] == 0


@pytest.mark.parametrize(
    "values", [[-1], [float("nan")], [float("inf")], [True], ["1"], [], [1] * 10001]
)
def test_bad_custom_values_are_rejected_by_contract(values):
    with pytest.raises(ValidationError):
        RainfallOptionsInput(
            mode="custom", start_seconds=0, time_step_seconds=300, values_mm=values
        )


@pytest.mark.parametrize("mode", ["real", "custom"])
def test_no_silent_duration_or_output_step_change(design, settings, mode):
    request = (
        {"mode": "real", "event_id": EVENT_ID}
        if mode == "real"
        else {"mode": "custom", "start_seconds": 0, "time_step_seconds": 300, "values_mm": [1] * 13}
    )
    with pytest.raises(ParameterValidationError, match="超过模拟时长"):
        apply_rainfall_scenario(design, "JJ", settings, rainfall_options=request)


def test_cannot_shorten_duration_without_replacing_rain(observed, settings):
    with pytest.raises(ParameterValidationError, match="现有降雨序列"):
        apply_rainfall_scenario(
            observed,
            "JJ",
            settings,
            {"duration_seconds": 3600, "report_step_seconds": 300},
            rainfall_mode="real",
        )
    # Replacement in the same save can make the new duration valid.
    content, _ = apply_rainfall_scenario(
        observed,
        "JJ",
        settings,
        {"duration_seconds": 3600, "report_step_seconds": 300},
        {"mode": "custom", "start_seconds": 0, "time_step_seconds": 300, "values_mm": [1, 0]},
        rainfall_mode="real",
    )
    assert build_simulation_options(INPParser.parse(content), settings)["duration_seconds"] == 3600


def test_laocheng_supports_custom_but_not_jinjiang_event(settings):
    content = STUDY_AREA_SEEDS[0].inp_path.read_text(encoding="utf-8")
    apply_rainfall_scenario(
        content,
        "LC",
        settings,
        rainfall_options={
            "mode": "custom",
            "start_seconds": 0,
            "time_step_seconds": 300,
            "values_mm": [1, 0],
        },
    )
    with pytest.raises(ParameterValidationError, match="老城"):
        prepare_rainfall({"mode": "real", "event_id": EVENT_ID}, "LC", 172800)


def test_contract_and_legacy_metadata():
    assert RainfallOptionsInput(mode="real", event_id=EVENT_ID).mode == "real"
    assert (
        RainfallOptionsInput(start_seconds=0, duration_seconds=3600, total_rainfall_mm=50).mode
        == "design"
    )
    assert ModelVersion(change_summary=None).rainfall_mode == "design"
    assert ModelVersion(change_summary={"rainfall_mode": "custom"}).rainfall_mode == "custom"
    assert Settings.model_fields["simulation_duration_max_seconds"].default == 172800


@pytest.mark.parametrize("start,step", [(17, 61), (75, 61), (0, 300)])
def test_custom_series_runs_in_swmm_engine_with_exact_total(
    design, settings, tmp_path, start, step
):
    from swmm.toolkit import solver

    content, _ = apply_rainfall_scenario(
        design,
        "JJ",
        settings,
        rainfall_options={
            "mode": "custom",
            "start_seconds": start,
            "time_step_seconds": step,
            "values_mm": [0, 1, 2, 0],
        },
    )
    inp = tmp_path / "custom.inp"
    inp.write_text(content, encoding="utf-8")
    solver.swmm_run(str(inp), str(inp.with_suffix(".rpt")), str(inp.with_suffix(".out")))
    report = inp.with_suffix(".rpt").read_text(encoding="utf-8")
    assert "ERROR" not in report
    precipitation = next(line for line in report.splitlines() if "Total Precipitation" in line)
    assert float(precipitation.split()[-1]) == pytest.approx(3.0, abs=0.001)


class MemoryStorage:
    def __init__(self):
        self.files = {}
        self.uploads = []

    def upload_model_version(self, path, model_id, version_id):
        key = str(version_id)
        self.files[key] = Path(path).read_bytes()
        self.uploads.append(key)
        return SimpleNamespace(
            bucket="test", object_key=key, checksum="test", size_bytes=len(self.files[key])
        )

    def download_to(self, key, path, **kwargs):
        Path(path).write_bytes(self.files[key])


class MemorySession:
    def __init__(self):
        self.model = SwmmModel(id=STUDY_AREA_SEEDS[1].model_id, name="JJ")
        self.versions = {}
        self.parameter_changes = []

    def get(self, kind, key, **kwargs):
        return self.model if kind is SwmmModel else self.versions.get(key)

    def scalar(self, query):
        return max((v.version for v in self.versions.values()), default=0)

    def add(self, item):
        self.versions[item.id] = item

    def add_all(self, items):
        self.parameter_changes.extend(items)

    def commit(self):
        pass

    def flush(self):
        pass

    def refresh(self, item):
        pass


def test_service_switches_source_on_current_engineering_version_and_preserves_history(
    design, settings
):
    service = object.__new__(ModelService)
    service.settings, service.storage = settings, MemoryStorage()
    session = MemorySession()
    seed = STUDY_AREA_SEEDS[1]
    parent = ModelVersion(
        id=seed.version_id,
        model_id=seed.model_id,
        version=3,
        inp_bucket="test",
        inp_object_key=str(seed.version_id),
        change_summary={"rainfall_mode": "design"},
    )
    session.versions[parent.id] = parent
    original = design.encode()
    service.storage.files[parent.inp_object_key] = original
    service.get_version = lambda session, version_id: session.versions[version_id]
    before = INPParser.parse(design)
    target = next(line.split()[0] for line in before["CONDUITS"] if not line.startswith(";"))
    version, changes = service.create_adjusted_version(
        session,
        parent.id,
        [{"section": "CONDUITS", "target": target, "field": "roughness", "new_value": "0.02"}],
        rainfall_options={
            "mode": "custom",
            "start_seconds": 0,
            "time_step_seconds": 300,
            "values_mm": [1, 2, 0],
        },
    )
    assert version.parent_version_id == parent.id and version.version == 4
    assert version.rainfall_mode == "custom"
    assert service.storage.files[parent.inp_object_key] == original
    assert {change["field"] for change in changes} == {"roughness", "rainfall_series"}
    first_bytes = service.storage.files[str(version.id)]
    # Engineering-only derivation leaves the custom rainfall byte-for-byte unchanged.
    newer, _ = service.create_adjusted_version(
        session,
        version.id,
        [{"section": "CONDUITS", "target": target, "field": "roughness", "new_value": "0.03"}],
    )
    a, b = [
        INPParser.parse(data.decode())
        for data in [first_bytes, service.storage.files[str(newer.id)]]
    ]
    assert a["TIMESERIES"] == b["TIMESERIES"] and a["RAINGAGES"] == b["RAINGAGES"]
    assert newer.rainfall_mode == "custom"
