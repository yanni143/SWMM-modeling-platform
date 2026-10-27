from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from config import Settings
from schemas.parameter import RainfallOptions, RainfallOptionsInput
from study_areas import STUDY_AREA_SEEDS
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
def settings():
    return SimpleNamespace(
        simulation_duration_min_seconds=60,
        simulation_duration_max_seconds=172800,
        report_step_min_seconds=10,
        simulation_require_report_step_divisible=False,
        simulation_max_output_steps=1000,
    )


@pytest.fixture
def design():
    return STUDY_AREA_SEEDS[1].inp_path.read_text(encoding="utf-8")


def to_real(content, settings):
    return apply_rainfall_scenario(
        content, "JJ", settings, rainfall_options={"mode": "real", "event_id": EVENT_ID}
    )[0]


def test_event_statistics_use_cumulative_increments(settings):
    event = real_event(settings)
    assert event["total_rainfall_mm"] == 226.2
    assert event["peak_rainfall_mm_h"] == pytest.approx(132.0)
    assert event["simulation_duration_seconds"] == 172800
    assert event["start_datetime"] == "2026-09-13T00:00:00"
    assert event["end_datetime"] == "2026-09-15T00:00:00"
    assert event["time_step_seconds"] == 300
    # The copy in resources must retain the supplied observations exactly.
    original = Path(__file__).resolve().parents[2] / "realdata/JJ_real_20260913_2d.inp"
    if original.exists():
        assert RESOURCE.read_bytes() == original.read_bytes()


def test_only_jinjiang_offers_real_rainfall(design, settings):
    sections = INPParser.parse(design)
    jj = RainfallOptions.model_validate(rainfall_catalog(sections, "JJ", settings))
    lc = RainfallOptions.model_validate(rainfall_catalog(sections, "LC", settings))
    assert jj.available_modes == ["design", "real"]
    assert jj.real_event.event_id == EVENT_ID
    assert lc.available_modes == ["design"]
    assert lc.real_event is None
    with pytest.raises(ParameterValidationError, match="老城"):
        apply_rainfall_scenario(design, "LC", settings, rainfall_options={"mode": "real"})


def test_real_transition_preserves_engineering_and_other_series(design, settings):
    original = INPParser.parse(design)
    target = original["CONDUITS"][2].split()[0]
    adjusted, _ = apply_parameter_changes(
        design,
        [{"section": "CONDUITS", "target": target, "field": "roughness", "new_value": "0.02"}],
    )
    # Keep another series, such as a tide or inflow, untouched.
    adjusted = adjusted.replace("[TIMESERIES]", "[TIMESERIES]\nOTHER 07/15/2025 00:00:00 1.5")
    observed = to_real(adjusted, settings)
    before = INPParser.parse(adjusted)
    after = INPParser.parse(observed)
    for section in before.keys() - {"OPTIONS", "RAINGAGES", "TIMESERIES"}:
        assert before[section] == after[section]
    assert "OTHER 07/15/2025 00:00:00 1.5" in after["TIMESERIES"]
    assert any("CUMULATIVE 00:05 1.0" in line for line in after["RAINGAGES"])
    simulation = build_simulation_options(after, settings)
    assert simulation["duration_seconds"] == 172800
    assert simulation["start_datetime"] == "2026-09-13T00:00:00"
    assert simulation["end_datetime"] == "2026-09-15T00:00:00"
    assert len([line for line in after["TIMESERIES"] if line.startswith("TS1H50_CHI ")]) == 577
    catalog = rainfall_catalog(after, "JJ", settings)
    assert catalog["mode"] == "real"
    assert catalog["read_only"] is True
    assert catalog["duration_seconds"] == 172800
    assert catalog["total_rainfall_mm"] == 226.2


def test_engineering_only_and_report_step_changes_preserve_real_series(design, settings):
    observed = to_real(design, settings)
    before = INPParser.parse(observed)
    target = next(line.split()[0] for line in before["CONDUITS"] if not line.startswith(";"))
    adjusted, engineering_changes = apply_parameter_changes(
        observed,
        [{"section": "CONDUITS", "target": target, "field": "roughness", "new_value": "0.02"}],
    )
    saved, changes = apply_rainfall_scenario(adjusted, "JJ", settings)
    assert saved == adjusted
    assert engineering_changes and not changes
    saved, changes = apply_rainfall_scenario(
        saved,
        "JJ",
        settings,
        simulation_options={"duration_seconds": 172800, "report_step_seconds": 600},
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
def test_real_conditions_cannot_be_overridden(design, settings, rain, simulation, message):
    with pytest.raises(ParameterValidationError, match=message):
        apply_rainfall_scenario(to_real(design, settings), "JJ", settings, simulation, rain)


def test_switching_back_restores_design_dates_and_rain_format(design, settings):
    original = INPParser.parse(design)
    simulation = build_simulation_options(original, settings)
    rain = build_rainfall_options(original, simulation["duration_seconds"])
    restored, changes = apply_rainfall_scenario(
        to_real(design, settings), "JJ", settings, rainfall_options={"mode": "design"}
    )
    after = INPParser.parse(restored)
    assert build_simulation_options(after, settings) == simulation
    result = rainfall_catalog(after, "JJ", settings)
    assert result["mode"] == "design"
    assert result["read_only"] is False
    for field in ("start_seconds", "duration_seconds", "total_rainfall_mm"):
        assert result[field] == pytest.approx(rain[field])
    assert any("INTENSITY 0:05" in line for line in after["RAINGAGES"])
    assert not any(
        line.startswith((";@REAL_RAIN", ";@DESIGN_BACKUP")) for line in after["TIMESERIES"]
    )
    assert any(item["field"] == "rainfall_mode" for item in changes)


@pytest.mark.parametrize("seed", STUDY_AREA_SEEDS)
def test_both_study_areas_allow_two_days_and_reject_longer(seed, settings):
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


def test_new_contract_accepts_event_only_and_legacy_design_payloads():
    assert RainfallOptionsInput(mode="real", event_id=EVENT_ID).mode == "real"
    assert (
        RainfallOptionsInput(start_seconds=0, duration_seconds=3600, total_rainfall_mm=50.0).mode
        == "design"
    )
    with pytest.raises(ValidationError):
        RainfallOptionsInput(mode="design")
    assert Settings.model_fields["simulation_duration_max_seconds"].default == 172800


def test_volume_and_reset_cumulative_statistics(settings):
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


def test_real_switch_adapts_short_report_step_and_restores_it(design, settings):
    content, _ = apply_simulation_options(
        design,
        INPParser.parse(design),
        {
            "duration_seconds": 3600,
            "report_step_seconds": 60,
        },
        settings,
    )
    observed = to_real(content, settings)
    assert (
        build_simulation_options(INPParser.parse(observed), settings)["report_step_seconds"] == 300
    )
    restored, _ = apply_rainfall_scenario(
        observed, "JJ", settings, rainfall_options={"mode": "design"}
    )
    assert (
        build_simulation_options(INPParser.parse(restored), settings)["report_step_seconds"] == 60
    )
