from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from config import Settings
from models.domain import ModelVersion, SwmmModel
from schemas.parameter import RainfallOptions, RainfallOptionsInput
from Service.ModelService import ModelService
from study_areas import JJ_REAL_INPUT_PATH, JJ_REAL_VERSION_ID, STUDY_AREA_SEEDS, rainfall_inputs
from Tools.InpTools.InpParameterEditor import (
    ParameterValidationError,
    apply_parameter_changes,
    apply_simulation_options,
    build_simulation_options,
)
from Tools.InpTools.InpParser import INPParser
from Tools.InpTools.InpRainfallEditor import build_rainfall_options
from Tools.InpTools.RainfallScenario import (
    EVENT_ID,
    RESOURCE,
    apply_rainfall_scenario,
    rainfall_catalog,
    real_event,
)


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


def test_event_statistics_use_cumulative_increments(settings):
    event = real_event(settings)
    assert event["total_rainfall_mm"] == 226.2
    assert event["peak_rainfall_mm_h"] == pytest.approx(132.0)
    assert event["simulation_duration_seconds"] == 172800
    assert event["start_datetime"] == "2026-09-13T00:00:00"
    assert event["end_datetime"] == "2026-09-15T00:00:00"
    assert event["time_step_seconds"] == 300
    original = Path(__file__).resolve().parents[2] / "realdata/JJ_real_20260913_2d.inp"
    if original.exists():
        assert RESOURCE.read_bytes() == original.read_bytes()


def test_only_jinjiang_has_two_input_roots():
    lc, jj = STUDY_AREA_SEEDS
    assert [item["mode"] for item in rainfall_inputs(lc.model_id)] == ["design"]
    inputs = rainfall_inputs(jj.model_id)
    assert [item["mode"] for item in inputs] == ["design", "real"]
    assert inputs[0]["baseline_version_id"] == jj.version_id
    assert inputs[1]["baseline_version_id"] == JJ_REAL_VERSION_ID
    assert inputs[1]["filename"] == JJ_REAL_INPUT_PATH.name


def test_raw_observed_input_is_read_only_without_rewriting_file(observed, settings):
    sections = INPParser.parse(observed)
    catalog = RainfallOptions.model_validate(rainfall_catalog(sections, "JJ", settings, "real"))
    assert catalog.mode == "real"
    assert catalog.read_only is True
    assert catalog.duration_seconds == 172800
    assert catalog.total_rainfall_mm == 226.2
    assert catalog.series_name == "TS_REAL_20260913"
    # Raw client data has no generated scenario marker or design backup.
    assert ";@REAL_RAIN" not in observed
    assert ";@DESIGN_BACKUP" not in observed
    result, changes = apply_rainfall_scenario(observed, "JJ", settings, rainfall_mode="real")
    assert result == observed
    assert changes == []


def test_laocheng_rejects_real_input(observed, settings):
    with pytest.raises(ParameterValidationError, match="老城"):
        apply_rainfall_scenario(observed, "LC", settings, rainfall_mode="real")


@pytest.mark.parametrize("from_mode,to_mode", [("design", "real"), ("real", "design")])
def test_parameter_save_cannot_switch_input(design, observed, settings, from_mode, to_mode):
    content = observed if from_mode == "real" else design
    with pytest.raises(ParameterValidationError, match="输入方案选择"):
        apply_rainfall_scenario(
            content, "JJ", settings, rainfall_options={"mode": to_mode}, rainfall_mode=from_mode
        )


def test_engineering_and_report_step_edits_preserve_observed_series(observed, settings):
    before = INPParser.parse(observed)
    target = next(line.split()[0] for line in before["CONDUITS"] if not line.startswith(";"))
    adjusted, engineering_changes = apply_parameter_changes(
        observed,
        [{"section": "CONDUITS", "target": target, "field": "roughness", "new_value": "0.02"}],
    )
    saved, changes = apply_rainfall_scenario(adjusted, "JJ", settings, rainfall_mode="real")
    assert saved == adjusted
    assert engineering_changes and not changes
    saved, changes = apply_rainfall_scenario(
        saved,
        "JJ",
        settings,
        simulation_options={"duration_seconds": 172800, "report_step_seconds": 600},
        rainfall_mode="real",
    )
    after = INPParser.parse(saved)
    assert after["TIMESERIES"] == before["TIMESERIES"]
    assert after["RAINGAGES"] == before["RAINGAGES"]
    assert build_simulation_options(after, settings)["report_step_seconds"] == 600


@pytest.mark.parametrize(
    "rain,simulation,message",
    [
        ({"mode": "real", "total_rainfall_mm": 300.0}, None, "不可修改"),
        ({"mode": "real", "start_seconds": 300}, None, "不可修改"),
        ({"mode": "real", "duration_seconds": 3600}, None, "不可修改"),
        ({"mode": "real", "event_id": "unknown"}, None, "不支持"),
        (None, {"duration_seconds": 86400, "report_step_seconds": 300}, "固定"),
    ],
)
def test_real_conditions_cannot_be_overridden(observed, settings, rain, simulation, message):
    with pytest.raises(ParameterValidationError, match=message):
        apply_rainfall_scenario(observed, "JJ", settings, simulation, rain, rainfall_mode="real")


@pytest.mark.parametrize("seed", STUDY_AREA_SEEDS)
def test_both_design_inputs_allow_two_days_and_reject_longer(seed, settings):
    content = seed.inp_path.read_text(encoding="utf-8")
    result, _ = apply_rainfall_scenario(
        content,
        seed.name,
        settings,
        {
            "duration_seconds": 172800,
            "report_step_seconds": 300,
        },
    )
    assert build_simulation_options(INPParser.parse(result), settings)["duration_seconds"] == 172800
    with pytest.raises(ParameterValidationError, match="172800"):
        apply_simulation_options(
            content,
            INPParser.parse(content),
            {
                "duration_seconds": 172801,
                "report_step_seconds": 300,
            },
            settings,
        )


def test_contract_accepts_real_validation_and_legacy_design_payloads():
    assert RainfallOptionsInput(mode="real", event_id=EVENT_ID).mode == "real"
    assert (
        RainfallOptionsInput(start_seconds=0, duration_seconds=3600, total_rainfall_mm=50.0).mode
        == "design"
    )
    with pytest.raises(ValidationError):
        RainfallOptionsInput(mode="design")
    assert Settings.model_fields["simulation_duration_max_seconds"].default == 172800
    assert ModelVersion(change_summary=None).rainfall_mode == "design"
    assert ModelVersion(change_summary={"rainfall_mode": "real"}).rainfall_mode == "real"


def test_volume_and_reset_cumulative_statistics():
    content = """[OPTIONS]
FLOW_UNITS LPS
START_DATE 09/13/2026
START_TIME 00:00:00
[RAINGAGES]
G1 CUMULATIVE 00:05 1 TIMESERIES RAIN
[TIMESERIES]
RAIN 09/13/2026 00:00:00 2
RAIN 09/13/2026 00:05:00 5
RAIN 09/13/2026 00:10:00 1
"""
    cumulative = build_rainfall_options(INPParser.parse(content), 3600)
    assert cumulative["total_rainfall_mm"] == 6
    assert cumulative["peak_rainfall_mm_h"] == 36
    volume = build_rainfall_options(INPParser.parse(content.replace("CUMULATIVE", "VOLUME")), 3600)
    assert volume["total_rainfall_mm"] == 8
    assert volume["peak_rainfall_mm_h"] == 60


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
        return max((v.version for v in self.versions.values()), default=7)

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


def test_observed_input_is_seeded_once_with_full_original_bytes(settings):
    service = object.__new__(ModelService)
    service.settings = settings
    service.storage = MemoryStorage()
    session = MemorySession()
    baseline = service._ensure_real_input(session)
    again = service._ensure_real_input(session)
    assert again is baseline
    assert len(service.storage.uploads) == 1
    assert service.storage.files[str(JJ_REAL_VERSION_ID)] == JJ_REAL_INPUT_PATH.read_bytes()
    assert baseline.parent_version_id is None
    assert baseline.rainfall_mode == "real"
    assert baseline.version == 8  # Do not overwrite any existing version number.
    assert session.parameter_changes == []


def test_engineering_save_inherits_real_input_and_parent(settings):
    service = object.__new__(ModelService)
    service.settings = settings
    service.storage = MemoryStorage()
    session = MemorySession()
    baseline = service._ensure_real_input(session)
    service.get_version = lambda session, version_id: session.versions[version_id]
    source = INPParser.parse(JJ_REAL_INPUT_PATH.read_text(encoding="utf-8"))
    target = next(line.split()[0] for line in source["CONDUITS"] if not line.startswith(";"))
    version, changes = service.create_adjusted_version(
        session,
        baseline.id,
        [{"section": "CONDUITS", "target": target, "field": "roughness", "new_value": "0.02"}],
    )
    assert version.parent_version_id == baseline.id
    assert version.rainfall_mode == "real"
    assert version.version == 9
    adjusted = INPParser.parse(service.storage.files[str(version.id)].decode("utf-8"))
    assert adjusted["TIMESERIES"] == source["TIMESERIES"]
    assert adjusted["RAINGAGES"] == source["RAINGAGES"]
    assert [item["field"] for item in changes] == ["roughness"]
